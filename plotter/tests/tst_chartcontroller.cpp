#include "core/AisModel.h"
#include "core/ChartController.h"
#include "core/Overlays.h"
#include "core/Settings.h"
#include "core/Store.h"
#include "core/Tracks.h"
#include "core/VesselModel.h"
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSet>
#include <QTemporaryDir>
#include <QtTest>
#include <cmath>
#include <memory>

namespace {
constexpr double kPi = 3.14159265358979323846;
const QList<double> kValdco{0, 0.9, 1.8, 3.6, 5, 5.4, 9.1, 10, 18.2, 20, 27.4, 30};
const QStringList kImageIds{OverlayIds::kBoatImage, OverlayIds::kAisImageA, OverlayIds::kAisImageB,
                            OverlayIds::kAisImageHollow};
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
    void setGeoJson(const QString& source, const QJsonObject& fc) override {
        calls << "geojson:" + source;
        sources[source] = fc;
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

// The runtime overlays are complete: images, four sources, layers above all style layers in the
// order tracks, active track, ais, own, and the depcnt-safety filter.
void checkOverlays(const FakeChartMap& map) {
    for (const QString& id : kImageIds) QVERIFY2(map.images.contains(id), qPrintable(id));
    QCOMPARE(QSet<QString>(map.sources.keyBegin(), map.sources.keyEnd()), kSources);
    const int nStyle = styleLayerCount(map.styles.last());
    QVERIFY(map.layerIds.size() >= nStyle + 7);
    QStringList runtimeSources;
    for (int i = nStyle; i < map.layerIds.size(); ++i) {
        const QString src = map.layerSrc.value(map.layerIds[i]);
        QVERIFY2(kSources.contains(src), qPrintable(map.layerIds[i]));
        runtimeSources << src;
    }
    QCOMPARE(map.layerIds.size() - nStyle, map.layerSrc.size()); // no runtime layer below a style layer
    QStringList order = runtimeSources;
    order.removeDuplicates();
    QCOMPARE(order, QStringList({OverlayIds::kTracksSource, OverlayIds::kActiveTrackSource, OverlayIds::kAisSource,
                                 OverlayIds::kOwnSource}));
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
        QCOMPARE(r.settings->chartMode(), QStringLiteral("fish"));
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
        QCOMPARE(r.settings->chartMode(), QStringLiteral("nav"));
        QCOMPARE(r.map.styles.size(), 1);
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

    void depthFilterErrorKeepsStyleFilters() {
        Rig r;
        QVERIFY(r.settings);
        // A depth literal the rule cannot map (7.7 m is none of the style's recorded depths).
        const QString path = r.chartsDir() + "/styles/nav-day.json";
        QFile f(path);
        QVERIFY(f.open(QIODevice::ReadOnly));
        QJsonObject style = QJsonDocument::fromJson(f.readAll()).object();
        f.close();
        QJsonArray layers = style["layers"].toArray();
        for (int i = 0; i < layers.size(); ++i) {
            QJsonObject l = layers[i].toObject();
            if (l["id"].toString() == "depare-deep") l["filter"] = json(R"([">=",["to-number",["get","DRVAL1"]],7.7])");
            layers[i] = l;
        }
        style["layers"] = layers;
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Truncate));
        f.write(QJsonDocument(style).toJson());
        f.close();
        r.make();
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("^ChartController: depth filters not applied:"));
        r.map.loaded();
        QVERIFY(r.map.filters.isEmpty());
        QCOMPARE(r.map.sources.size(), 4); // the overlays are still there
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
