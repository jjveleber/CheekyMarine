#include "core/AisModel.h"
#include "core/ChartController.h"
#include "core/Geo.h"
#include "core/Overlays.h"
#include "core/Settings.h"
#include "core/Store.h"
#include "core/Tracks.h"
#include "core/VesselModel.h"
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSet>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>
#include <cmath>
#include <memory>

namespace {
constexpr double kPi = 3.14159265358979323846;
const QList<double> kValdco{0, 0.9, 1.8, 3.6, 5, 5.4, 9.1, 10, 18.2, 20, 27.4, 30};
const QStringList kImageIds{OverlayIds::kBoatImage, OverlayIds::kAisImageA, OverlayIds::kAisImageB,
                            OverlayIds::kAisImageHollow, OverlayIds::kCogTipImage};
const QSet<QString> kSources{OverlayIds::kTracksSource, OverlayIds::kActiveTrackSource, OverlayIds::kAisSource,
                             OverlayIds::kOwnSource};

QJsonValue json(const QByteArray& text) { return QJsonDocument::fromJson("[" + text + "]").array().at(0); }

// Records what the controller does to the map. Mimics MapLibre: a style load drops runtime images,
// sources, layers and filter changes; added layers go on top.
class FakeChartMap : public ChartMap {
public:
    struct Camera {
        double lat, lon, zoom, bearing;
    };
    bool syncStyleLoaded = false; // emit styleLoaded inside setStyleJson, like the real adapter
    double zoomValue = 13;
    double height = 600;
    // When set, setGeoJson serializes the collection to compact text as MapLibreChartPort does, and
    // records the time it took and the size.
    bool serialize = false;
    qint64 serializeNs = 0;
    qsizetype serializedBytes = 0;

    QList<QJsonObject> styles;        // every style loaded
    QStringList calls;                // "style", "filter:<layer>", "geojson:<source>", "image:<id>", "layer:<id>"
    QStringList layerIds;             // current stack, bottom first
    QHash<QString, QString> layerSrc; // runtime layer id -> source
    QHash<QString, QJsonValue> filters;
    QHash<QString, QJsonObject> sources;
    QSet<QString> images;
    QHash<QString, QImage> imageData;   // last image added per id
    QHash<QString, QJsonObject> layers; // runtime layers added since the last style load
    QList<Camera> cameras;

    void setStyleJson(const QByteArray& style) override {
        const QJsonObject s = QJsonDocument::fromJson(style).object();
        styles << s;
        calls << "style";
        layerIds.clear();
        layerSrc.clear();
        for (const auto& l : s["layers"].toArray()) layerIds << l.toObject()["id"].toString();
        filters.clear();
        sources.clear();
        images.clear();
        layers.clear();
        if (syncStyleLoaded) emit styleLoaded();
    }
    void setLayerFilter(const QString& layer, const QJsonValue& filter) override {
        calls << "filter:" + layer;
        filters[layer] = filter;
    }
    void setPaintProperty(const QString& layer, const QString& property, const QJsonValue& value) override {
        calls << "paint:" + layer + ":" + property;
        patch(layer, "paint", property, value);
    }
    void setLayoutProperty(const QString& layer, const QString& property, const QJsonValue& value) override {
        calls << "layout:" + layer + ":" + property;
        patch(layer, "layout", property, value);
    }
    void setGeoJson(const QString& source, const QJsonObject& fc) override {
        calls << "geojson:" + source;
        sources[source] = fc;
        if (serialize) {
            QElapsedTimer t;
            t.start();
            serializedBytes = QJsonDocument(fc).toJson(QJsonDocument::Compact).size();
            serializeNs = t.nsecsElapsed();
        }
    }
    void addImage(const QString& id, const QImage& image) override {
        calls << "image:" + id;
        images << id;
        imageData[id] = image;
    }
    void addLayer(const QJsonObject& layer) override {
        const QString id = layer["id"].toString();
        calls << "layer:" + id;
        layerIds << id;
        layerSrc[id] = layer["source"].toString();
        layers[id] = layer;
    }
    void setCamera(double lat, double lon, double zoom, double bearing) override {
        cameras << Camera{lat, lon, zoom, bearing};
        zoomValue = zoom;
    }
    void setZoom(double zoom) override { zoomValue = zoom; }
    double zoom() const override { return zoomValue; }
    double viewportHeight() const override { return height; }
    QPointF toScreen(double lat, double lon) const override {
        return {(lon + 122.23) * 10000.0 + 512, (47.98 - lat) * 10000.0 + 300};
    }

    // A null value resets the property to the style default (removes it).
    void patch(const QString& layer, const QString& group, const QString& property, const QJsonValue& value) {
        if (!layers.contains(layer)) return;
        QJsonObject l = layers[layer];
        QJsonObject g = l[group].toObject();
        if (value.isNull()) g.remove(property);
        else g[property] = value;
        l[group] = g;
        layers[layer] = l;
    }

    void loaded() { emit styleLoaded(); }
    void gesture() { emit userGesture(); }
    void resize(double h) {
        height = h;
        emit viewportChanged();
    }
    int count(const QString& call) const { return static_cast<int>(calls.count(call)); }
};

bool copyStyles(const QString& dir) {
    if (!QDir().mkpath(dir + "/styles")) return false;
    const QDir src(QStringLiteral(PLOTTER_FIXTURES "/styles"));
    for (const QString& f : src.entryList({"*.json"}, QDir::Files))
        if (!QFile::copy(src.filePath(f), dir + "/styles/" + f)) return false;
    return true;
}

// Replaces the filter of layer `id` in the style file at `path`.
bool setLayerFilter(const QString& path, const QString& id, const QJsonValue& filter) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) return false;
    QJsonObject style = QJsonDocument::fromJson(f.readAll()).object();
    f.close();
    QJsonArray layers = style["layers"].toArray();
    for (int i = 0; i < layers.size(); ++i) {
        QJsonObject l = layers[i].toObject();
        if (l["id"].toString() == id) l["filter"] = filter;
        layers[i] = l;
    }
    style["layers"] = layers;
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    return f.write(QJsonDocument(style).toJson()) > 0;
}

// Adds the bathy pack's `bathy` source to the style file at `path`.
bool addBathySource(const QString& path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) return false;
    QJsonObject style = QJsonDocument::fromJson(f.readAll()).object();
    f.close();
    QJsonObject sources = style["sources"].toObject();
    sources["bathy"] = QJsonObject{{"type", "vector"}, {"url", "mbtiles://bathy"}};
    style["sources"] = sources;
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    return f.write(QJsonDocument(style).toJson()) > 0;
}

struct Rig {
    QTemporaryDir tmp;
    std::unique_ptr<Store> store;
    std::unique_ptr<Settings> settings;
    VesselModel vessel;
    AisModel ais;
    FakeChartMap map;
    QList<PackInfo> packs;
    std::unique_ptr<ChartController> ctrl;

    // bathy: install a bathy pack; zooms: charts pack min/max zoom (-1 = absent).
    explicit Rig(bool bathy = true, bool sync = false, int minZoom = 6, int maxZoom = 16) {
        auto st = Store::open(tmp.path() + "/data");
        if (!st) return;
        store = std::move(*st);
        settings = std::make_unique<Settings>(*store);
        const QString charts = tmp.path() + "/packs/charts-puget-north-1.0.0";
        const QString bathyDir = tmp.path() + "/packs/bathy-puget-north-1.0.0";
        if (!copyStyles(charts) || !copyStyles(bathyDir)) return;
        PackInfo c;
        c.kind = "charts";
        c.region = "puget-north";
        c.version = QVersionNumber(1, 0, 0);
        c.dir = charts;
        c.valdco = kValdco;
        c.minZoom = minZoom;
        c.maxZoom = maxZoom;
        packs << c;
        if (bathy) {
            PackInfo b;
            b.kind = "bathy";
            b.region = "puget-north";
            b.version = QVersionNumber(1, 0, 0);
            b.dir = bathyDir;
            packs << b;
        }
        map.syncStyleLoaded = sync;
        vessel.setLive(true);
        ais.setLive(true);
    }
    QString chartsDir() const { return tmp.path() + "/packs/charts-puget-north-1.0.0"; }
    ChartController& make() {
        ctrl = std::make_unique<ChartController>(map, *settings, vessel, ais, packs);
        QHash<QString, QImage> imgs;
        for (const QString& id : kImageIds) imgs[id] = QImage(8, 8, QImage::Format_ARGB32_Premultiplied);
        ctrl->setImages(imgs);
        return *ctrl;
    }
};

QString paletteOf(const QJsonObject& style) {
    return style["metadata"].toObject()["cheekymarine"].toObject()["palette"].toString();
}
QString spriteOf(const QJsonObject& style) { return style["sprite"].toString(); }
int styleLayerCount(const QJsonObject& style) { return static_cast<int>(style["layers"].toArray().size()); }

VesselState boat() {
    VesselState v;
    v.lat = 47.98;
    v.lon = -122.23;
    return v;
}

// The runtime overlays are complete: images, four sources, and exactly these layers above all
// style layers, bottom first (tracks, active track, ais, own).
void checkOverlays(const FakeChartMap& map) {
    for (const QString& id : kImageIds) QVERIFY2(map.images.contains(id), qPrintable(id));
    QCOMPARE(QSet<QString>(map.sources.keyBegin(), map.sources.keyEnd()), kSources);
    const int nStyle = styleLayerCount(map.styles.last());
    QCOMPARE(map.layerIds.mid(nStyle),
             QStringList({"cm-tracks-line", "cm-track-active-line", "cm-ais-vector", "cm-ais-icon", "cm-own-heading",
                          "cm-own-cog", "cm-own-cog-tip", "cm-own-boat"}));
    for (int i = nStyle; i < map.layerIds.size(); ++i)
        QVERIFY2(kSources.contains(map.layerSrc.value(map.layerIds[i])), qPrintable(map.layerIds[i]));
    QCOMPARE(map.layerIds.size() - nStyle, map.layerSrc.size()); // no runtime layer below a style layer
    QCOMPARE(QSet<QString>(map.layerIds.begin(), map.layerIds.end()).size(), map.layerIds.size());
}
} // namespace

// checkOverlays() reports through QVERIFY; stop the test at its first failure.
#define CHECK_OVERLAYS(map)                                                                                            \
    do {                                                                                                               \
        checkOverlays(map);                                                                                            \
        if (QTest::currentTestFailed()) return;                                                                        \
    } while (false)

class TstChartController : public QObject {
    Q_OBJECT
private slots:
    void initialLoadIsNavDay() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QCOMPARE(r.map.styles.size(), 1);
        QCOMPARE(paletteOf(r.map.styles[0]), QStringLiteral("day"));
        QCOMPARE(spriteOf(r.map.styles[0]), "file://" + r.chartsDir() + "/sprites/nav");
        QCOMPARE(r.map.styles[0]["sources"].toObject()["enc"].toObject()["url"].toString(),
                 "mbtiles://" + r.chartsDir() + "/enc.mbtiles");
        QCOMPARE(r.ctrl->mode(), QStringLiteral("nav"));
        QVERIFY(r.ctrl->fishAvailable());
        QCOMPARE(r.ctrl->notice(),
                 QStringLiteral("Derived from NOAA ENC. Not an official chart. Not certified for navigation."));
    }

    void fishLoadsFishDay() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.ctrl->setMode("fish");
        QCOMPARE(r.ctrl->mode(), QStringLiteral("fish"));
        QCOMPARE(r.map.styles.size(), 2);
        QVERIFY(spriteOf(r.map.styles[1]).endsWith("/bathy-puget-north-1.0.0/sprites/fish"));
        QCOMPARE(paletteOf(r.map.styles[1]), QStringLiteral("day"));
        QVERIFY(r.ctrl->notice().startsWith("Fishing chart"));
    }

    void fishRefusedWithoutBathy() {
        Rig r(false);
        QVERIFY(r.settings);
        r.make();
        QVERIFY(!r.ctrl->fishAvailable());
        QTest::ignoreMessage(QtWarningMsg, "ChartController: no bathy pack for the charts region, staying in nav");
        r.ctrl->setMode("fish");
        QCOMPARE(r.ctrl->mode(), QStringLiteral("nav"));
        QCOMPARE(r.map.styles.size(), 1);
    }

    // The mode is the current view's, not a setting: a plan 3 chartMode row does not change the start.
    void startsInNav() {
        Rig r;
        QVERIFY(r.settings);
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec(R"(INSERT INTO settings VALUES('chartMode','"fish"'))"));
        r.settings = std::make_unique<Settings>(*r.store); // reads the rows afresh
        r.make();
        QCOMPARE(r.ctrl->mode(), QStringLiteral("nav"));
        QCOMPARE(r.map.styles.size(), 1);
        QCOMPARE(spriteOf(r.map.styles[0]), "file://" + r.chartsDir() + "/sprites/nav");
        QCOMPARE(paletteOf(r.map.styles[0]), QStringLiteral("day"));
    }

    void setModeWritesNoSetting() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("SELECT group_concat(key || '=' || value) FROM settings") && q.next());
        const QString before = q.value(0).toString();
        r.ctrl->setMode("fish");
        QCOMPARE(r.ctrl->mode(), QStringLiteral("fish"));
        QVERIFY(q.exec("SELECT group_concat(key || '=' || value) FROM settings") && q.next());
        QCOMPARE(q.value(0).toString(), before);
    }

    void styleLoadedAddsOverlaysAndFilters() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QVERIFY(r.map.sources.isEmpty()); // nothing runtime before the style has loaded
        r.map.loaded();
        CHECK_OVERLAYS(r.map);
        QCOMPARE(r.map.filters.value("depcnt-safety"), json(R"(["==",["to-number",["get","VALDCO"]],3.6])"));
    }

    void depthChangeReappliesWithoutReload() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.map.calls.clear();
        QVERIFY(r.settings->setDepths(1.5, 4.0, 12.0));
        QVERIFY(r.map.calls.filter(QRegularExpression("^filter:")).size() > 0);
        QCOMPARE(r.map.count("style"), 0);
        QCOMPARE(r.map.filters.value("depcnt-safety"), json(R"(["==",["to-number",["get","VALDCO"]],5])"));
        QCOMPARE(r.map.filters.value("depare-vshallow"), json(R"(["<",["to-number",["get","DRVAL1"]],1.5])"));
    }

    // A pack whose style trips the depth filter check is refused with the reason (the list the
    // About page shows) and the next valid charts pack is used.
    void depthFilterErrorRefusesThePackAndUsesTheNext() {
        Rig r;
        QVERIFY(r.settings);
        const QString newer = r.tmp.path() + "/packs/charts-puget-north-1.1.0";
        QVERIFY(copyStyles(newer));
        // A depth read beside a numeric literal outside a plain comparison: the rule cannot map it.
        QVERIFY(setLayerFilter(newer + "/styles/nav-dusk.json", "depare-deep",
                               json(R"(["step",["to-number",["get","DRVAL1"]],false,9.144,true])")));
        PackInfo n = r.packs[0];
        n.version = QVersionNumber(1, 1, 0);
        n.dir = newer;
        r.packs << n;
        r.make();
        const QList<PackInfo> packs = r.ctrl->packs();
        QCOMPARE(packs.size(), 3);
        QVERIFY2(packs[2].refused.contains("nav-dusk.json") && packs[2].refused.contains("depare-deep"),
                 qPrintable(packs[2].refused));
        QVERIFY(packs[0].refused.isEmpty());
        QVERIFY(packs[1].refused.isEmpty());
        QCOMPARE(r.map.styles.size(), 1);
        QCOMPARE(spriteOf(r.map.styles[0]), "file://" + r.chartsDir() + "/sprites/nav");
        QVERIFY(r.ctrl->fishAvailable());
        r.map.loaded();
        CHECK_OVERLAYS(r.map);
        QCOMPARE(r.map.filters.value("depcnt-safety"), json(R"(["==",["to-number",["get","VALDCO"]],3.6])"));
    }

    // The only charts pack refused: nothing is loaded and nothing crashes.
    void depthFilterErrorOnTheOnlyChartsPackLoadsNothing() {
        Rig r;
        QVERIFY(r.settings);
        // 7.7 m is none of the style's recorded depths.
        QVERIFY(setLayerFilter(r.chartsDir() + "/styles/nav-day.json", "depare-deep",
                               json(R"([">=",["to-number",["get","DRVAL1"]],7.7])")));
        QTest::ignoreMessage(QtWarningMsg, "ChartController: no usable charts pack");
        r.make();
        QVERIFY2(r.ctrl->packs()[0].refused.contains("unmapped depth literal 7.7"),
                 qPrintable(r.ctrl->packs()[0].refused));
        QVERIFY(r.map.styles.isEmpty());
        QVERIFY(!r.ctrl->fishAvailable());
        r.vessel.setState(boat());
        r.ctrl->setPalette("night");
        QVERIFY(r.map.styles.isEmpty());
    }

    // A bathy pack whose fish style lists a depth layer it does not have is refused: no fishing mode.
    void depthFilterErrorRefusesTheBathyPack() {
        Rig r;
        QVERIFY(r.settings);
        const QString path = r.tmp.path() + "/packs/bathy-puget-north-1.0.0/styles/fish-night.json";
        QFile f(path);
        QVERIFY(f.open(QIODevice::ReadOnly));
        QJsonObject style = QJsonDocument::fromJson(f.readAll()).object();
        f.close();
        QJsonArray layers;
        for (const auto& l : style["layers"].toArray())
            if (l.toObject()["id"].toString() != "hazard-danger") layers << l;
        style["layers"] = layers;
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Truncate));
        f.write(QJsonDocument(style).toJson());
        f.close();
        r.make();
        QVERIFY2(r.ctrl->packs()[1].refused.contains("fish-night.json") &&
                     r.ctrl->packs()[1].refused.contains("hazard-danger"),
                 qPrintable(r.ctrl->packs()[1].refused));
        QVERIFY(r.ctrl->packs()[0].refused.isEmpty());
        QVERIFY(!r.ctrl->fishAvailable());
        QCOMPARE(r.ctrl->mode(), QStringLiteral("nav"));
        QCOMPARE(r.map.styles.size(), 1);
        QCOMPARE(spriteOf(r.map.styles[0]), "file://" + r.chartsDir() + "/sprites/nav");
    }

    // The start check prepares each style with the same pack directories as the runtime load: a nav
    // style that uses the bathy source passes when a bathy pack is there, and loads from it.
    void navStyleWithBathySourcePassesWithABathyPack() {
        Rig r;
        QVERIFY(r.settings);
        QVERIFY(addBathySource(r.chartsDir() + "/styles/nav-day.json"));
        r.make();
        QVERIFY2(r.ctrl->packs()[0].refused.isEmpty(), qPrintable(r.ctrl->packs()[0].refused));
        QCOMPARE(r.map.styles.size(), 1);
        QCOMPARE(r.map.styles[0]["sources"].toObject()["bathy"].toObject()["url"].toString(),
                 "mbtiles://" + r.tmp.path() + "/packs/bathy-puget-north-1.0.0/bathy.mbtiles");
    }

    // Without a bathy pack the runtime load could not use that style either, so the pack is refused.
    void navStyleWithBathySourceRefusedWithoutABathyPack() {
        Rig r(false);
        QVERIFY(r.settings);
        QVERIFY(addBathySource(r.chartsDir() + "/styles/nav-day.json"));
        QTest::ignoreMessage(QtWarningMsg, "ChartController: no usable charts pack");
        r.make();
        QVERIFY2(r.ctrl->packs()[0].refused.startsWith("styles/nav-day.json: "), qPrintable(r.ctrl->packs()[0].refused));
        QVERIFY(r.map.styles.isEmpty());
    }

    // The styles are parsed once at start: a file removed afterwards is not read again.
    void stylesAreReadOnceAtStart() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QVERIFY(QFile::remove(r.chartsDir() + "/styles/nav-night.json"));
        r.ctrl->setPalette("night");
        QCOMPARE(r.map.styles.size(), 2);
        QCOMPARE(r.map.styles[1]["name"].toString(), QStringLiteral("CheekyMarine nav night"));
    }

    void paletteReloadReaddsRuntimeSources() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.ctrl->setPalette("night");
        QCOMPARE(r.map.styles.size(), 2);
        QCOMPARE(paletteOf(r.map.styles[1]), QStringLiteral("night"));
        QVERIFY(r.map.sources.isEmpty()); // the reload dropped them
        r.map.loaded();
        CHECK_OVERLAYS(r.map);
        QCOMPARE(r.map.filters.value("depcnt-safety"), json(R"(["==",["to-number",["get","VALDCO"]],3.6])"));
    }

    void reentrantStyleLoaded() {
        Rig r(true, true);
        QVERIFY(r.settings);
        r.make();
        CHECK_OVERLAYS(r.map);
        QCOMPARE(r.map.count("filter:depcnt-safety"), 1);
        const int layersPerLoad = r.map.layerSrc.size();
        QCOMPARE(r.map.calls.filter(QRegularExpression("^layer:")).size(), layersPerLoad);
        r.map.calls.clear();
        r.ctrl->setPalette("dusk");
        CHECK_OVERLAYS(r.map);
        QCOMPARE(r.map.count("style"), 1);
        QCOMPARE(r.map.count("filter:depcnt-safety"), 1);
        QCOMPARE(r.map.calls.filter(QRegularExpression("^layer:")).size(), layersPerLoad);
        for (const QString& id : kImageIds) QCOMPARE(r.map.count("image:" + id), 1);
        QCOMPARE(r.map.toScreen(47.98, -122.23), QPointF(512, 300));
    }

    void cogTipLayerAboveCog() {
        Rig r(true, true);
        QVERIFY(r.settings);
        r.make();
        const int cog = r.map.layerIds.indexOf("cm-own-cog");
        QVERIFY(cog >= 0);
        QCOMPARE(r.map.layerIds.at(cog + 1), QStringLiteral("cm-own-cog-tip"));
        QCOMPARE(r.map.layerIds.at(cog + 2), QStringLiteral("cm-own-boat"));
        const QJsonObject tip = r.map.layers.value("cm-own-cog-tip");
        QCOMPARE(tip["type"].toString(), QStringLiteral("symbol"));
        QCOMPARE(tip["source"].toString(), OverlayIds::kOwnSource);
        QCOMPARE(tip["layout"].toObject()["icon-image"].toString(), OverlayIds::kCogTipImage);
        QCOMPARE(tip["layout"].toObject()["icon-rotation-alignment"].toString(), QStringLiteral("map"));
    }

    void headingAndCogSettingsRepushOwnShip() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        VesselState v = boat();
        v.hdgRad = 0.5;
        v.hdgRef = "True";
        v.cogRad = 0.5;
        v.sogMs = 5.0;
        r.vessel.setState(v);
        const auto kinds = [&] {
            QStringList k;
            for (const auto& f : r.map.sources.value(OverlayIds::kOwnSource)["features"].toArray())
                k << f.toObject()["properties"].toObject()["kind"].toString();
            return k;
        };
        const auto cogLenM = [&] {
            for (const auto& f : r.map.sources.value(OverlayIds::kOwnSource)["features"].toArray()) {
                const QJsonObject o = f.toObject();
                if (o["properties"].toObject()["kind"].toString() != "cog") continue;
                const QJsonArray c = o["geometry"].toObject()["coordinates"].toArray();
                const auto at = [&](int i) {
                    return LatLon{c.at(i).toArray().at(1).toDouble(), c.at(i).toArray().at(0).toDouble()};
                };
                return distanceM(at(0), at(1));
            }
            return -1.0;
        };
        QVERIFY(kinds().contains("heading"));
        QVERIFY(kinds().contains("cog"));
        QVERIFY(kinds().contains("cogtip"));
        QVERIFY(std::abs(cogLenM() - 300.0) < 3.0); // 1 min default
        r.map.calls.clear();
        r.settings->setShowHeadingLine(false);
        QVERIFY(!kinds().contains("heading"));
        QVERIFY(kinds().contains("cog"));
        r.settings->setCogLineMin(5);
        QVERIFY(std::abs(cogLenM() - 1500.0) < 15.0); // SOG x 300 s
        r.settings->setShowCogLine(false);
        QVERIFY(!kinds().contains("cog"));
        QVERIFY(!kinds().contains("cogtip"));
        QCOMPARE(r.map.count("style"), 0);
    }

    void trackStyleFromSettings_data() {
        QTest::addColumn<QString>("type");
        QTest::addColumn<QString>("dash");
        QTest::addColumn<QString>("cap");
        QTest::newRow("solid") << "solid" << "" << "butt";
        QTest::newRow("dashed") << "dashed" << "[4,2]" << "butt";
        QTest::newRow("dotted") << "dotted" << "[0.1,2]" << "round";
        QTest::newRow("dashdot") << "dashdot" << "[4,2,0.1,2]" << "round";
    }
    void trackStyleFromSettings() {
        QFETCH(QString, type);
        QFETCH(QString, dash);
        QFETCH(QString, cap);
        const QStringList ids{"cm-tracks-line", "cm-track-active-line"};
        const auto check = [&](Rig& r, const QString& t, const QString& d, const QString& c, const QString& colour) {
            for (const QString& id : ids) {
                const QJsonObject paint = r.map.layers.value(id)["paint"].toObject();
                QCOMPARE(paint["line-color"].toString(), colour);
                if (d.isEmpty()) QVERIFY2(!paint.contains("line-dasharray"), qPrintable(id + " " + t));
                else QCOMPARE(paint["line-dasharray"], json(d.toUtf8()));
                QCOMPARE(r.map.layers.value(id)["layout"].toObject()["line-cap"].toString(), c);
            }
        };
        // At load.
        {
            Rig r;
            QVERIFY(r.settings);
            r.settings->setTrackLineType(type);
            r.settings->setTrackColor("#123456");
            r.make();
            r.map.loaded();
            check(r, type, dash, cap, "#123456");
        }
        // At runtime, then kept over a palette reload.
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.map.calls.clear();
        r.settings->setTrackLineType(type);
        r.settings->setTrackColor("#654321");
        QCOMPARE(r.map.count("style"), 0);
        for (const QString& id : ids) {
            QVERIFY(r.map.calls.contains("paint:" + id + ":line-color"));
            QVERIFY(r.map.calls.contains("paint:" + id + ":line-dasharray") || type == "dashed");
            QVERIFY(r.map.calls.contains("layout:" + id + ":line-cap") || type == "dashed");
        }
        check(r, type, dash, cap, "#654321");
        r.ctrl->setPalette("dusk");
        r.map.loaded();
        check(r, type, dash, cap, trackColour(QColor("#654321"), "dusk").name());
    }

    // Owner hands-on (PR #70): a Track line change on the real map showed the previous dash, or
    // nothing for solid, until a style reload. MapLibre holds a non-interpolatable property such as
    // line-dasharray at its prior value for the whole paint transition (300 ms by default), builds
    // the line drawables from that prior value, and does not rebuild them when the transition ends.
    // A zero dasharray transition makes a runtime dash change take effect in the same frame.
    void trackDashChangesWithoutTransition() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        for (const char* id : {"cm-tracks-line", "cm-track-active-line"}) {
            const QJsonObject paint = r.map.layers.value(id)["paint"].toObject();
            QVERIFY2(paint.contains("line-dasharray-transition"), id);
            QCOMPARE(paint["line-dasharray-transition"].toObject()["duration"].toInt(-1), 0);
            QCOMPARE(paint["line-dasharray-transition"].toObject()["delay"].toInt(-1), 0); // a root delay can't apply
        }
        r.map.calls.clear();
        r.settings->setTrackLineType("solid");
        QCOMPARE(r.map.count("style"), 0); // still applied in place, not by a style reload
    }

    void trackNightIsAmberWhateverChosen() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setTrackColor("#00ff00");
        r.make();
        r.ctrl->setPalette("night");
        r.map.loaded();
        for (const char* id : {"cm-tracks-line", "cm-track-active-line"})
            QCOMPARE(r.map.layers.value(id)["paint"].toObject()["line-color"].toString(),
                     overlayColours("night").track.name());
    }

    void displaySettingsBeforeReadyApplyOnLoad() {
        Rig r; // styleLoaded not yet emitted
        QVERIFY(r.settings);
        r.make();
        r.settings->setShowHeadingLine(false);
        r.settings->setShowCogLine(false);
        r.settings->setCogLineMin(5);
        r.settings->setTrackLineType("dotted");
        r.settings->setTrackColor("#00ff00");
        VesselState v = boat();
        v.hdgRad = 0.5;
        v.hdgRef = "True";
        v.cogRad = 0.5;
        v.sogMs = 5.0;
        r.vessel.setState(v);
        QCOMPARE(r.map.count("paint:cm-tracks-line:line-color"), 0);
        r.map.loaded();
        for (const char* id : {"cm-tracks-line", "cm-track-active-line"}) {
            const QJsonObject l = r.map.layers.value(id);
            QCOMPARE(l["paint"].toObject()["line-color"].toString(), QStringLiteral("#00ff00"));
            QCOMPARE(l["paint"].toObject()["line-dasharray"], json("[0.1,2]"));
            QCOMPARE(l["layout"].toObject()["line-cap"].toString(), QStringLiteral("round"));
        }
        QCOMPARE(r.map.sources.value(OverlayIds::kOwnSource)["features"].toArray().size(), 1); // boat only
    }

    void northUpCentresOnBoat() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setOrientation("north");
        r.make();
        r.map.loaded();
        r.vessel.setState(boat());
        QVERIFY(!r.map.cameras.isEmpty());
        const auto c = r.map.cameras.last();
        QCOMPARE(c.lat, 47.98);
        QCOMPARE(c.lon, -122.23);
        QCOMPARE(c.bearing, 0.0);
        QVERIFY(!r.ctrl->noPosition());
    }

    void startPositionCentersTheMapWithoutAFix() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setOrientation("north");
        r.make();
        r.ctrl->setStartPosition(47.5, -122.5);
        r.map.loaded();
        QVERIFY(!r.map.cameras.isEmpty());
        QCOMPARE(r.map.cameras.last().lat, 47.5);
        QCOMPARE(r.map.cameras.last().lon, -122.5);
        QCOMPARE(r.map.cameras.last().bearing, 0.0);
        r.vessel.setState(boat());
        QCOMPARE(r.map.cameras.last().lat, 47.98);
        QCOMPARE(r.map.cameras.last().lon, -122.23);
    }

    void headUpTrueHeadingAndLowerThird() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QCOMPARE(r.ctrl->orientation(), QStringLiteral("head"));
        r.map.loaded();
        VesselState v = boat();
        v.hdgRad = 1.0;
        v.hdgRef = "Magnetic";
        v.variationRad = 0.2731;
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        const auto c = r.map.cameras.last();
        const double expBearing = (1.0 + 0.2731) * 180.0 / kPi;
        QVERIFY2(std::abs(c.bearing - expBearing) < 1e-6, qPrintable(QString::number(c.bearing)));
        const LatLon want = destination({47.98, -122.23}, expBearing, 600.0 / 6 * metresPerPixel(47.98, c.zoom));
        QVERIFY2(distanceM({c.lat, c.lon}, want) < 0.5, qPrintable(QString::number(distanceM({c.lat, c.lon}, want))));
    }

    void headUpFallsBackToCog() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 3;
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QVERIFY(std::abs(r.map.cameras.last().bearing - 90.0) < 1e-6);
    }

    void headUpSlowIsNorth() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 0.1;
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QCOMPARE(r.map.cameras.last().bearing, 0.0);
    }

    void courseUpUsesCog() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setOrientation("course");
        r.make();
        QCOMPARE(r.ctrl->orientation(), QStringLiteral("course"));
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 3;
        v.hdgRad = 1.0; // COG wins in course-up
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        const auto c = r.map.cameras.last();
        QVERIFY(std::abs(c.bearing - 90.0) < 1e-6);
        const LatLon want = destination({47.98, -122.23}, 90.0, 600.0 / 6 * metresPerPixel(47.98, c.zoom));
        QVERIFY(distanceM({c.lat, c.lon}, want) < 0.5);
        QVERIFY(c.lon > -122.23);
    }

    // Spec 6.6: magnetic heading without variation is not a true heading; head-up uses COG, else north.
    void headUpMagneticWithoutVariationUsesCog() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        VesselState v = boat();
        v.hdgRad = 1.0;
        v.hdgRef = "Magnetic";
        v.cogRad = kPi / 2;
        v.sogMs = 3;
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QVERIFY2(std::abs(r.map.cameras.last().bearing - 90.0) < 1e-6,
                 qPrintable(QString::number(r.map.cameras.last().bearing)));
        v.sogMs = 0.1;
        r.vessel.setState(v);
        QCOMPARE(r.map.cameras.last().bearing, 0.0);
        v.hdgRef.clear(); // no reference: not true either
        v.variationRad = 0.2731;
        r.vessel.setState(v);
        QCOMPARE(r.map.cameras.last().bearing, 0.0);
    }

    void courseUpSlowMagneticWithoutVariationIsNorth() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setOrientation("course");
        r.make();
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 0.1;
        v.hdgRad = 1.0;
        v.hdgRef = "Magnetic";
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QCOMPARE(r.map.cameras.last().bearing, 0.0);
    }

    void courseUpSlowUsesHeading() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setOrientation("course");
        r.make();
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 0.1;
        v.hdgRad = 1.0;
        v.hdgRef = "True";
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QVERIFY(std::abs(r.map.cameras.last().bearing - 180.0 / kPi) < 1e-6);
    }

    void gestureStopsFollowRecenterResumes() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.vessel.setState(boat());
        QVERIFY(r.ctrl->follow());
        const auto n = r.map.cameras.size();
        r.map.gesture();
        QVERIFY(!r.ctrl->follow());
        r.vessel.setState(boat());
        QCOMPARE(r.map.cameras.size(), n);
        r.ctrl->recenter();
        QVERIFY(r.ctrl->follow());
        QCOMPARE(r.map.cameras.size(), n + 1);
    }

    void zoomRangeAndClamp() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QCOMPARE(r.ctrl->minZoom(), 6.0);
        QCOMPARE(r.ctrl->maxZoom(), 18.0);
        r.map.zoomValue = 17;
        r.ctrl->zoomIn();
        QCOMPARE(r.map.zoom(), 18.0);
        r.ctrl->zoomIn();
        QCOMPARE(r.map.zoom(), 18.0);
        r.map.zoomValue = 7;
        r.ctrl->zoomOut();
        r.ctrl->zoomOut();
        QCOMPARE(r.map.zoom(), 6.0);
        r.vessel.setState(boat()); // the follow camera keeps the zoom
        QVERIFY(!r.map.cameras.isEmpty());
        QCOMPARE(r.map.cameras.last().zoom, 6.0);
    }

    void zoomWhileFollowingKeepsBoatPlacement() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        VesselState v = boat();
        v.cogRad = kPi / 2;
        v.sogMs = 3;
        r.vessel.setState(v); // head-up falls back to COG 90
        r.map.zoomValue = 13;
        const auto placedAt = [&](double zoom) {
            return destination({47.98, -122.23}, 90.0, 600.0 / 6 * metresPerPixel(47.98, zoom));
        };
        for (const auto& step : {std::pair{1.5, 14.5}, std::pair{10.0, 18.0}, std::pair{-1.0, 17.0}}) {
            const auto n = r.map.cameras.size();
            if (step.first == -1.0) r.ctrl->zoomOut();
            else r.ctrl->zoomBy(step.first);
            QVERIFY(r.ctrl->follow());
            QCOMPARE(r.map.cameras.size(), n + 1);
            const auto c = r.map.cameras.last();
            QCOMPARE(c.zoom, step.second);
            QVERIFY(std::abs(c.bearing - 90.0) < 1e-6);
            QVERIFY(distanceM({c.lat, c.lon}, placedAt(step.second)) < 0.5);
        }
        r.ctrl->zoomIn(); // at 17
        QVERIFY(r.ctrl->follow());
        QCOMPARE(r.map.cameras.last().zoom, 18.0);
        QVERIFY(distanceM({r.map.cameras.last().lat, r.map.cameras.last().lon}, placedAt(18)) < 0.5);
        r.ctrl->zoomBy(-20);
        QCOMPARE(r.map.cameras.last().zoom, 6.0);
    }

    // The legend sheet's rows: the charts pack's legend entries as {abbr, meaning, kind}, in order.
    void legendIsTheChartsPackEntries() {
        Rig r;
        QVERIFY(r.settings);
        r.packs[0].legend = {{"Blds", "boulders", "type"}, {"bk", "broken", "qualifier"}};
        r.make();
        const QVariantList l = r.ctrl->legend();
        QCOMPARE(l.size(), 2);
        QCOMPARE(l[0].toMap(), (QVariantMap{{"abbr", "Blds"}, {"meaning", "boulders"}, {"kind", "type"}}));
        QCOMPARE(l[1].toMap(), (QVariantMap{{"abbr", "bk"}, {"meaning", "broken"}, {"kind", "qualifier"}}));
    }
    void legendEmptyWithoutAChartsPack() {
        Rig r;
        QVERIFY(r.settings);
        r.packs.clear();
        QTest::ignoreMessage(QtWarningMsg, "ChartController: no usable charts pack");
        r.make();
        QVERIFY(r.ctrl->legend().isEmpty());
    }

    // The legend categories are rebuilt on every style load: mode and palette changes reload the style.
    void legendFollowsModeAndPalette() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        const auto ids = [&r] {
            QStringList out;
            for (const QVariant& c : r.ctrl->legendCategories()) out << c.toMap()["id"].toString();
            return out;
        };
        QVERIFY(ids().contains("navaids"));
        QCOMPARE(r.ctrl->spriteBase(), r.chartsDir() + "/sprites/nav");
        QSignalSpy changed(r.ctrl.get(), &ChartController::legendCategoriesChanged);
        r.ctrl->setMode("fish");
        QCOMPARE(changed.count(), 1);
        QVERIFY(!ids().contains("navaids"));
        QVERIFY(r.ctrl->spriteBase().endsWith("/bathy-puget-north-1.0.0/sprites/fish"));
        QVERIFY(!r.ctrl->spriteBase().startsWith("file:"));
        r.map.loaded();
        r.ctrl->setPalette("night");
        QCOMPARE(changed.count(), 2);
        int hazardSprites = 0;
        for (const QVariant& c : r.ctrl->legendCategories()) {
            if (c.toMap()["id"] != "hazards") continue;
            for (const QVariant& row : c.toMap()["rows"].toList()) {
                const QString sprite = row.toMap()["sprite"].toString();
                if (!sprite.startsWith("hazard-")) continue;
                ++hazardSprites;
                QVERIFY2(sprite.endsWith("-night"), qPrintable(sprite));
            }
        }
        QVERIFY(hazardSprites >= 4);
    }

    void legendWithoutPackIsAisOnly() {
        Rig r;
        QVERIFY(r.settings);
        r.packs.clear();
        QTest::ignoreMessage(QtWarningMsg, "ChartController: no usable charts pack");
        r.make();
        const QVariantList cats = r.ctrl->legendCategories();
        QVERIFY(!cats.isEmpty());
        for (const QVariant& c : cats) {
            const QVariantMap m = c.toMap();
            if (m["id"] == "ais") {
                QCOMPARE(m["rows"].toList().size(), 4);
            } else {
                QVERIFY(m["rows"].toList().isEmpty());
                QVERIFY(m["needsPack"].toBool());
            }
        }
        QCOMPARE(r.ctrl->spriteBase(), QString());
    }

    void zoomRangeFallbackWithoutMetadata() {
        Rig r(true, false, -1, -1);
        QVERIFY(r.settings);
        r.make();
        QCOMPARE(r.ctrl->minZoom(), 0.0);
        QCOMPARE(r.ctrl->maxZoom(), 22.0);
        r.map.zoomValue = 21;
        r.ctrl->zoomIn();
        r.ctrl->zoomIn();
        QCOMPARE(r.map.zoom(), 22.0);
    }

    void noPositionAndNotLiveClearsOwnShip() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QVERIFY(r.ctrl->noPosition());
        r.vessel.setState(boat());
        QVERIFY(!r.ctrl->noPosition());
        QCOMPARE(r.map.sources.value(OverlayIds::kOwnSource)["features"].toArray().size(), 1);
        r.vessel.setLive(false);
        QVERIFY(r.ctrl->noPosition());
        QVERIFY(r.map.sources.value(OverlayIds::kOwnSource)["features"].toArray().isEmpty());
    }

    void aisAndTracksReachTheMap() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        AisTarget t;
        t.mmsi = 367000001;
        t.cls = "A";
        t.lat = 47.99;
        t.lon = -122.25;
        r.ais.setTargets({t});
        QCOMPARE(r.map.sources.value(OverlayIds::kAisSource)["features"].toArray().size(), 1);
        r.ctrl->setTracks({{{47.98, -122.23}, {47.99, -122.24}}});
        QCOMPARE(r.map.sources.value(OverlayIds::kTracksSource)["features"].toArray().size(), 1);
        r.ctrl->setPalette("night");
        r.map.loaded(); // survive a reload
        QCOMPARE(r.map.sources.value(OverlayIds::kAisSource)["features"].toArray().size(), 1);
        QCOMPARE(r.map.sources.value(OverlayIds::kTracksSource)["features"].toArray().size(), 1);
    }

    // The #46 write cost: one active-track write at 7200 points, the controller's build and the
    // serialization the real port does on the main thread, under 50 ms together.
    // --frame-stats turns on write timing: each active-track write records its main-thread time.
    void writeTimingRecordsEachActiveTrackWrite() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QVERIFY(r.ctrl->writeTimesUs().isEmpty());
        r.ctrl->setActiveTrack({{47.98, -122.23}}); // off: not recorded
        QVERIFY(r.ctrl->writeTimesUs().isEmpty());
        r.ctrl->setWriteTiming(true);
        r.ctrl->setActiveTrack({{47.98, -122.23}});
        r.ctrl->setActiveTrack({{47.98, -122.23}, {47.99, -122.24}});
        r.ctrl->setActiveTrack({});
        r.ctrl->setTracks({{{47.98, -122.23}, {47.99, -122.24}}}); // finished tracks are not counted
        const QList<qint64> times = r.ctrl->writeTimesUs();
        QCOMPARE(times.size(), 3);
        for (qint64 us : times) QVERIFY(us >= 0);
    }

    void activeTrackWriteCostAt7200Points() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        // 2 h at 1 Hz and 26 kn: 7200 points 13.4 m apart along the navigating route of synth_n2k.py.
        const QList<LatLon> pts = syntheticTrack(7200);
        QCOMPARE(pts.size(), 7200);
        r.map.calls.clear();
        r.map.serialize = true;
        QElapsedTimer timer;
        timer.start();
        r.ctrl->setActiveTrack(pts); // the fake map serializes inside, as the real port does
        const double ms = timer.nsecsElapsed() / 1e6;
        const double serializeMs = r.map.serializeNs / 1e6;
        const QJsonObject fc = r.map.sources.value(OverlayIds::kActiveTrackSource);
        qInfo().noquote() << QStringLiteral("active-track write: build %1 ms, serialize %2 ms, total %3 ms, %4 bytes")
                                 .arg(ms - serializeMs, 0, 'f', 2)
                                 .arg(serializeMs, 0, 'f', 2)
                                 .arg(ms, 0, 'f', 2)
                                 .arg(r.map.serializedBytes);
        QVERIFY(r.map.serializeNs > 0);
        QVERIFY(r.map.serializedBytes > 100000);
        QCOMPARE(r.map.calls.count(QStringLiteral("geojson:") + OverlayIds::kActiveTrackSource), 1);
        const QJsonArray feats = fc["features"].toArray();
        QCOMPARE(feats.size(), 1);
        const QJsonObject geom = feats.at(0).toObject()["geometry"].toObject();
        QCOMPARE(geom["type"].toString(), QStringLiteral("LineString"));
        QCOMPARE(geom["coordinates"].toArray().size(), 7200);
        QVERIFY2(ms < 50, qPrintable(QStringLiteral("active track write took %1 ms").arg(ms)));
    }

    // The seed prefix (--seed-track) goes ahead of every active-track write and is never stored.
    void seedTrackPrefixesEveryActiveWrite() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        const auto coords = [&r] {
            const QJsonObject fc = r.map.sources.value(OverlayIds::kActiveTrackSource);
            return fc["features"].toArray().at(0).toObject()["geometry"].toObject()["coordinates"].toArray();
        };
        r.ctrl->setSeedTrack({{1, 2}, {3, 4}, {5, 6}});
        r.ctrl->setActiveTrack({{7, 8}, {9, 10}});
        QJsonArray c = coords();
        QCOMPARE(c.size(), 5);
        QCOMPARE(c.at(0).toArray().at(0).toDouble(), 2.0); // lon first
        QCOMPARE(c.at(0).toArray().at(1).toDouble(), 1.0);
        QCOMPARE(c.at(2).toArray().at(1).toDouble(), 5.0);
        QCOMPARE(c.at(3).toArray().at(1).toDouble(), 7.0);
        r.ctrl->setActiveTrack({});
        QCOMPARE(coords().size(), 3);
        r.ctrl->setActiveTrack({{7, 8}, {9, 10}});
        r.ctrl->setPalette("night");
        r.map.loaded(); // a style reload rewrites the source: the seed must survive it
        QCOMPARE(coords().size(), 5);
        r.ctrl->setActiveTrack({});
        r.ctrl->setSeedTrack({});
        r.ctrl->setActiveTrack({});
        const QJsonObject fc = r.map.sources.value(OverlayIds::kActiveTrackSource);
        QCOMPARE(fc, tracksGeoJson({{}}));
    }

    // A kept point re-sends only the active track; the finished tracks go to the map when the set
    // or a visibility changes, and both survive a style reload.
    void keptPointSendsOnlyTheActiveTrack() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setTrackRecording(true);
        r.settings->setTrackIntervalS(1);
        r.settings->setTrackMinDistanceM(0);
        r.make();
        r.map.loaded();
        TrackStore store(*r.store);
        double now = 0;
        TrackRecorder rec(store, *r.settings, [&now] { return now; });
        TracksController tracks(store, rec);
        bindTracks(*r.ctrl, tracks);
        const auto feed = [&](double t, double lat) {
            now = t;
            VesselState s = boat();
            s.t = t;
            s.lat = lat;
            rec.onVessel(s);
        };
        const auto features = [&](const char* source) {
            return r.map.sources.value(source)["features"].toArray().size();
        };
        feed(0, 47.0);
        feed(1, 47.001);
        feed(1000, 48.0); // a gap: the first track is finished
        QCOMPARE(features(OverlayIds::kTracksSource), 1);
        const int finishedCalls = r.map.count(QStringLiteral("geojson:") + OverlayIds::kTracksSource);
        const int activeCalls = r.map.count(QStringLiteral("geojson:") + OverlayIds::kActiveTrackSource);
        feed(1001, 48.001);
        feed(1002, 48.002);
        QCOMPARE(r.map.count(QStringLiteral("geojson:") + OverlayIds::kTracksSource), finishedCalls);
        QCOMPARE(r.map.count(QStringLiteral("geojson:") + OverlayIds::kActiveTrackSource), activeCalls + 2);
        QCOMPARE(features(OverlayIds::kActiveTrackSource), 1);
        tracks.refresh(); // the tracks page's 5 s refresh
        QCOMPARE(r.map.count(QStringLiteral("geojson:") + OverlayIds::kTracksSource), finishedCalls);
        const qint64 first = tracks.tracks().at(1).toMap()["id"].toLongLong();
        tracks.setVisible(first, false);
        QCOMPARE(r.map.count(QStringLiteral("geojson:") + OverlayIds::kTracksSource), finishedCalls + 1);
        QCOMPARE(features(OverlayIds::kTracksSource), 0);
        tracks.setVisible(first, true);
        QCOMPARE(features(OverlayIds::kTracksSource), 1);
        r.ctrl->setPalette("night");
        r.map.loaded(); // a reload drops runtime sources; both come back
        QCOMPARE(features(OverlayIds::kTracksSource), 1);
        QCOMPARE(features(OverlayIds::kActiveTrackSource), 1);
        QCOMPARE(r.map.layerSrc.value("cm-track-active-line"), QString(OverlayIds::kActiveTrackSource));
    }

    // Three fixture targets: A at (47.990, -122.250), B 3 px right of A, C far away.
    static QList<AisTarget> fixtureTargets() {
        AisTarget a, b, c;
        a.mmsi = 367000001;
        a.cls = "A";
        a.name = "SEA QUEEN";
        a.lat = 47.99;
        a.lon = -122.25;
        a.sogMs = 5.144444;
        a.cogRad = kPi / 2;
        a.posAge = 12;
        b.mmsi = 367000002;
        b.cls = "B";
        b.lat = 47.99;
        b.lon = -122.2497;
        c.mmsi = 367000003;
        c.cls = "A";
        c.lat = 48.05;
        c.lon = -122.30;
        return {a, b, c};
    }

    void aisFeedsThreePointsClearsOnEmptyAndNotLive() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.ais.setTargets(fixtureTargets());
        const auto features = r.map.sources.value(OverlayIds::kAisSource)["features"].toArray();
        int points = 0;
        for (const auto& f : features)
            if (f.toObject()["properties"].toObject()["kind"].toString() == "ais") ++points;
        QCOMPARE(points, 3);
        r.ais.setTargets({});
        QVERIFY(r.map.sources.value(OverlayIds::kAisSource)["features"].toArray().isEmpty());
        r.ais.setTargets(fixtureTargets());
        QVERIFY(!r.map.sources.value(OverlayIds::kAisSource)["features"].toArray().isEmpty());
        r.ais.setLive(false);
        QVERIFY(r.map.sources.value(OverlayIds::kAisSource)["features"].toArray().isEmpty());
    }

    void targetAtPicksTheNearestWithinTheRadius() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.ais.setTargets(fixtureTargets());
        const QPointF a = r.map.toScreen(47.99, -122.25); // B is 3 px to its right
        // 2 px right of A: A is 2 px away, B is 1 px away, so B.
        QCOMPARE(r.ctrl->targetAt(a + QPointF(2, 0), 5).toUInt(), 367000002u);
        QCOMPARE(r.ctrl->targetAt(a + QPointF(-1, 0), 5).toUInt(), 367000001u);
        // Only B is inside a 2 px radius of a point 4 px right of A.
        QCOMPARE(r.ctrl->targetAt(a + QPointF(4, 0), 2).toUInt(), 367000002u);
        QVERIFY(!r.ctrl->targetAt(a + QPointF(0, 50), 8).isValid());
        QVERIFY(!r.ctrl->targetAt(QPointF(0, 0), 8).isValid());
        r.ais.setTargets({});
        QVERIFY(!r.ctrl->targetAt(a, 8).isValid());
    }

    void targetAtPicksTheNearerOfTwoCloseTargets() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QList<AisTarget> two = fixtureTargets();
        two[1].lon = -122.2470; // 30 px right of A at the fake map's 10000 px per degree
        r.ais.setTargets(two);
        const QPointF a = r.map.toScreen(47.99, -122.25);
        // 8 mm at 4.626 px/mm is 37 px: both targets are inside the radius.
        QCOMPARE(r.ctrl->targetAt(a + QPointF(5, 0), 37).toUInt(), 367000001u);
        QCOMPARE(r.ctrl->targetAt(a + QPointF(25, 0), 37).toUInt(), 367000002u);
    }

    void selectedTargetCarriesFormattedValuesAndTracksUpdates() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.vessel.setState(boat());
        r.ais.setTargets(fixtureTargets());
        QVERIFY(r.ctrl->aisSelection().isEmpty());
        const QPointF a = r.map.toScreen(47.99, -122.25);
        r.ctrl->selectAt(a + QPointF(-1, 0), 5);
        QVariantMap s = r.ctrl->aisSelection();
        QCOMPARE(s["mmsi"].toString(), QString("367000001"));
        QCOMPARE(s["name"].toString(), QString("SEA QUEEN"));
        QCOMPARE(s["cls"].toString(), QString("A"));
        QCOMPARE(s["sog"].toString(), QString("10.0"));
        QCOMPARE(s["cog"].toString(), QString("090"));
        QCOMPARE(s["posAge"].toString(), QString("12 s"));
        QCOMPARE(s["range"].toString(), QString("1.0")); // 1.1 km north, 1.5 km west
        QCOMPARE(s["bearing"].toString(), QString("307")); // NW of own ship
        // The target keeps moving: the selection follows it.
        QList<AisTarget> moved = fixtureTargets();
        moved[0].sogMs = 2.572222;
        r.ais.setTargets(moved);
        QCOMPARE(r.ctrl->aisSelection()["sog"].toString(), QString("5.0"));
        // A target with no name or position shows Unknown and "--".
        QList<AisTarget> bare = fixtureTargets();
        bare[0].name.clear();
        bare[0].lat.reset();
        bare[0].lon.reset();
        bare[0].sogMs.reset();
        bare[0].posAge.reset();
        r.ais.setTargets(bare);
        s = r.ctrl->aisSelection();
        QCOMPARE(s["name"].toString(), QString("Unknown"));
        QCOMPARE(s["range"].toString(), QString("--"));
        QCOMPARE(s["bearing"].toString(), QString("--"));
        QCOMPARE(s["sog"].toString(), QString("--"));
        QCOMPARE(s["posAge"].toString(), QString("--"));
        // The target disappears: the sheet closes.
        r.ais.setTargets({});
        QVERIFY(r.ctrl->aisSelection().isEmpty());
        // A miss clears nothing selected; clearTarget closes.
        r.ais.setTargets(fixtureTargets());
        r.ctrl->selectAt(a, 5);
        QVERIFY(!r.ctrl->aisSelection().isEmpty());
        r.ctrl->clearTarget();
        QVERIFY(r.ctrl->aisSelection().isEmpty());
        r.ctrl->selectAt(QPointF(0, 0), 5);
        QVERIFY(r.ctrl->aisSelection().isEmpty());
    }

    // A target whose position is over 60 s old (hollow on the chart) still shows range, bearing and
    // SOG from its last position; the age printed beside them tells the reader how old they are.
    void staleTargetKeepsValuesAndShowsAge() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        r.vessel.setState(boat());
        QList<AisTarget> targets = fixtureTargets();
        targets[0].posAge = 61;
        r.ais.setTargets(targets);
        r.ctrl->selectMmsi(367000001);
        const QVariantMap s = r.ctrl->aisSelection();
        QCOMPARE(s["posAge"].toString(), QString("61 s"));
        QCOMPARE(s["range"].toString(), QString("1.0"));
        QCOMPARE(s["bearing"].toString(), QString("307"));
        QCOMPARE(s["sog"].toString(), QString("10.0"));
    }

    void selectMmsiSelectsAKnownTargetAndClearsOnAnUnknownOne() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.ais.setTargets(fixtureTargets());
        QSignalSpy changed(r.ctrl.get(), &ChartController::aisSelectionChanged);
        r.ctrl->selectMmsi(367000002);
        QCOMPARE(r.ctrl->aisSelection()["mmsi"].toString(), QString("367000002"));
        QCOMPARE(changed.count(), 1);
        r.ctrl->selectMmsi(999999999);
        QVERIFY(r.ctrl->aisSelection().isEmpty());
        QCOMPARE(changed.count(), 2);
    }

    // The first camera can come while the viewport has no height yet; a resize re-applies it so
    // the boat lands in the lower third without waiting for the next vessel update.
    void viewportResizeReappliesFollowCamera() {
        Rig r;
        QVERIFY(r.settings);
        r.map.height = 0;
        r.make();
        r.map.loaded();
        VesselState v = boat();
        v.hdgRad = 0.5;
        v.hdgRef = "True";
        r.vessel.setState(v);
        QVERIFY(!r.map.cameras.isEmpty());
        QVERIFY(distanceM({r.map.cameras.last().lat, r.map.cameras.last().lon}, {47.98, -122.23}) < 0.01);
        const auto n = r.map.cameras.size();
        r.map.resize(600);
        QCOMPARE(r.map.cameras.size(), n + 1);
        const auto c = r.map.cameras.last();
        const double bearing = 0.5 * 180.0 / kPi;
        const LatLon want = destination({47.98, -122.23}, bearing, 600.0 / 6 * metresPerPixel(47.98, c.zoom));
        QVERIFY2(distanceM({c.lat, c.lon}, want) < 0.5, qPrintable(QString::number(distanceM({c.lat, c.lon}, want))));
        r.ctrl->setFollow(false);
        const auto m = r.map.cameras.size();
        r.map.resize(800); // not following: the camera is the user's
        QCOMPARE(r.map.cameras.size(), m);
    }

    // Runtime line colours follow the palette (night is red only).
    void paletteSetsRuntimeLineColours() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        const auto colourOf = [&](const char* layer) {
            return r.map.layers.value(layer)["paint"].toObject()["line-color"].toString();
        };
        QCOMPARE(colourOf("cm-own-heading"), overlayColours("day").heading.name());
        r.ctrl->setPalette("night");
        r.map.loaded();
        QCOMPARE(colourOf("cm-own-heading"), overlayColours("night").heading.name());
        QCOMPARE(colourOf("cm-own-cog"), overlayColours("night").cog.name());
        QCOMPARE(colourOf("cm-ais-vector"), overlayColours("night").aisVector.name());
        QCOMPARE(colourOf("cm-tracks-line"), overlayColours("night").track.name());
        QCOMPARE(colourOf("cm-track-active-line"), overlayColours("night").track.name());
    }

    // Images handed over before a palette change are the ones re-added after the reload.
    void paletteReloadReaddsNewImages() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.map.loaded();
        QHash<QString, QImage> red;
        for (const QString& id : kImageIds) {
            QImage img(8, 8, QImage::Format_ARGB32_Premultiplied);
            img.fill(QColor(0xc0, 0, 0));
            red[id] = img;
        }
        r.ctrl->setImages(red);
        r.ctrl->setPalette("night");
        QVERIFY(r.map.images.isEmpty());
        r.map.loaded();
        for (const QString& id : kImageIds) {
            QVERIFY2(r.map.images.contains(id), qPrintable(id));
            QCOMPARE(r.map.imageData.value(id).pixelColor(4, 4).rgb(), QColor(0xc0, 0, 0).rgb());
        }
    }
};

QTEST_GUILESS_MAIN(TstChartController)
#include "tst_chartcontroller.moc"
