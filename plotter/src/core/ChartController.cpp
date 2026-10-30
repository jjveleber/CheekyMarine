#include "core/ChartController.h"
#include "core/AisModel.h"
#include "core/DepthFilters.h"
#include "core/Overlays.h"
#include "core/Settings.h"
#include "core/StyleLoader.h"
#include "core/VesselModel.h"
#include <QDebug>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <algorithm>
#include <cmath>

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kMinCogSogMs = 0.2572; // 0.5 kn: below this COG is noise
constexpr double kStartZoom = 13;
constexpr double kOverzoom = 2;
constexpr double kFallbackMinZoom = 0, kFallbackMaxZoom = 22; // pack without zoom metadata

double degNorm(double radians) {
    double d = std::fmod(radians * 180.0 / kPi, 360.0);
    if (d < 0) d += 360.0;
    if (d >= 360.0) d = 0.0;
    return d;
}

std::optional<double> trueHeadingDeg(const VesselState& v) {
    if (!v.hdgRad) return std::nullopt;
    double h = *v.hdgRad;
    if (v.hdgRef == QLatin1String("Magnetic") && v.variationRad) h += *v.variationRad;
    return degNorm(h);
}

std::optional<double> cogDeg(const VesselState& v) {
    if (v.cogRad && v.sogMs && *v.sogMs > kMinCogSogMs) return degNorm(*v.cogRad);
    return std::nullopt;
}

QJsonObject parse(const char* json) { return QJsonDocument::fromJson(json).object(); }

// A line layer with its paint line-color set.
QJsonObject line(QJsonObject layer, const QColor& colour) {
    QJsonObject paint = layer[QStringLiteral("paint")].toObject();
    paint[QStringLiteral("line-color")] = colour.name();
    layer[QStringLiteral("paint")] = paint;
    return layer;
}

// Runtime layers, bottom first: tracks, AIS, own ship (topmost), in the palette's overlay colours.
QList<QJsonObject> runtimeLayers(const OverlayColours& c) {
    return {
        line(parse(R"({"id":"cm-tracks-line","type":"line","source":"cm-tracks",
            "filter":["==",["get","kind"],"track"],
            "layout":{"line-join":"round","line-cap":"round"},
            "paint":{"line-width":2.5}})"), c.track),
        line(parse(R"({"id":"cm-ais-vector","type":"line","source":"cm-ais",
            "filter":["==",["get","kind"],"aisvec"],
            "paint":{"line-width":1.5}})"), c.aisVector),
        parse(R"({"id":"cm-ais-icon","type":"symbol","source":"cm-ais",
            "filter":["==",["get","kind"],"ais"],
            "layout":{"icon-image":["case",["get","hollow"],"cm-ais-hollow",
                                    ["==",["get","cls"],"B"],"cm-ais-b","cm-ais-a"],
                      "icon-size":["case",["all",["get","hollow"],["==",["get","cls"],"B"]],0.75,1],
                      "icon-rotate":["get","rot"],"icon-rotation-alignment":"map",
                      "icon-allow-overlap":true,"icon-ignore-placement":true}})"),
        line(parse(R"({"id":"cm-own-heading","type":"line","source":"cm-own",
            "filter":["==",["get","kind"],"heading"],
            "paint":{"line-width":1.5}})"), c.heading),
        line(parse(R"({"id":"cm-own-cog","type":"line","source":"cm-own",
            "filter":["==",["get","kind"],"cog"],
            "paint":{"line-width":3,"line-dasharray":[2,1]}})"), c.cog),
        parse(R"({"id":"cm-own-boat","type":"symbol","source":"cm-own",
            "filter":["==",["get","kind"],"boat"],
            "layout":{"icon-image":"cm-boat","icon-rotate":["get","rot"],
                      "icon-rotation-alignment":"map",
                      "icon-allow-overlap":true,"icon-ignore-placement":true}})"),
    };
}
} // namespace

ChartController::ChartController(ChartMap& map, Settings& settings, VesselModel& vessel, AisModel& ais,
                                 QList<PackInfo> packs, QObject* parent)
    : QObject(parent), m_map(map), m_settings(settings), m_vessel(vessel), m_ais(ais) {
    m_charts = PackCatalog::best(packs, u"charts");
    if (m_charts) {
        for (const LegendEntry& e : m_charts->legend)
            m_legend.append(QVariantMap{{QStringLiteral("abbr"), e.abbr}, {QStringLiteral("meaning"), e.meaning},
                                        {QStringLiteral("kind"), e.kind}});
        m_bathy = PackCatalog::best(packs, u"bathy", m_charts->region);
        m_minZoom = m_charts->minZoom >= 0 ? m_charts->minZoom : kFallbackMinZoom;
        m_maxZoom = m_charts->maxZoom >= 0 ? m_charts->maxZoom + kOverzoom : kFallbackMaxZoom;
    } else {
        qWarning() << "ChartController: no usable charts pack";
    }
    if (m_settings.chartMode() == QLatin1String("fish") && fishAvailable()) m_mode = QStringLiteral("fish");

    // Connect before the first load: the real map emits styleLoaded inside setStyleJson.
    connect(&m_map, &ChartMap::styleLoaded, this, &ChartController::onStyleLoaded);
    connect(&m_map, &ChartMap::userGesture, this, [this] { setFollow(false); });
    connect(&m_map, &ChartMap::viewportChanged, this, &ChartController::applyCamera);
    connect(&m_settings, &Settings::shallowMChanged, this, &ChartController::applyDepthFilters);
    connect(&m_settings, &Settings::safetyMChanged, this, &ChartController::applyDepthFilters);
    connect(&m_settings, &Settings::deepMChanged, this, &ChartController::applyDepthFilters);
    connect(&m_settings, &Settings::orientationChanged, this, [this] {
        emit orientationChanged();
        applyCamera();
    });
    connect(&m_vessel, &VesselModel::changed, this, &ChartController::onVessel);
    connect(&m_ais, &QAbstractItemModel::modelReset, this, &ChartController::pushAis);

    m_map.setZoom(std::clamp(kStartZoom, m_minZoom, m_maxZoom));
    loadStyle();
}

void ChartController::setMode(const QString& mode) {
    if (mode == m_mode) return;
    if (mode != QLatin1String("nav") && mode != QLatin1String("fish")) {
        qWarning() << "ChartController: unknown mode" << mode;
        return;
    }
    if (mode == QLatin1String("fish") && !fishAvailable()) {
        qWarning() << "ChartController: no bathy pack for the charts region, staying in nav";
        emit modeChanged(); // lets a toggle bound to `mode` snap back
        return;
    }
    m_mode = mode;
    m_settings.setChartMode(mode);
    emit modeChanged();
    loadStyle();
}

QString ChartController::orientation() const { return m_settings.orientation(); }
void ChartController::setOrientation(const QString& orientation) { m_settings.setOrientation(orientation); }

void ChartController::setPalette(const QString& palette) {
    if (palette == m_palette) return;
    if (palette != QLatin1String("day") && palette != QLatin1String("dusk") && palette != QLatin1String("night")) {
        qWarning() << "ChartController: unknown palette" << palette;
        return;
    }
    m_palette = palette;
    emit paletteChanged();
    loadStyle();
}

void ChartController::setFollow(bool follow) {
    if (follow == m_follow) return;
    m_follow = follow;
    emit followChanged();
    applyCamera();
}

void ChartController::setImages(const QHash<QString, QImage>& images) {
    m_images = images;
    if (!m_ready) return;
    for (auto it = m_images.cbegin(); it != m_images.cend(); ++it) m_map.addImage(it.key(), it.value());
}

void ChartController::setTracks(const QList<QList<LatLon>>& tracks) {
    m_tracks = tracks;
    if (m_ready) m_map.setGeoJson(OverlayIds::kTracksSource, tracksGeoJson(m_tracks));
}

void ChartController::zoomIn() { zoomBy(1); }
void ChartController::zoomOut() { zoomBy(-1); }

void ChartController::recenter() {
    if (m_follow) applyCamera();
    else setFollow(true);
}

void ChartController::zoomBy(double log2Delta) {
    m_map.setZoom(std::clamp(m_map.zoom() + log2Delta, m_minZoom, m_maxZoom));
    applyCamera(); // the lower-third offset depends on the zoom
}

void ChartController::loadStyle() {
    if (!m_charts) return;
    const bool fish = m_mode == QLatin1String("fish");
    const QString packDir = fish ? m_bathy->dir : m_charts->dir;
    QFile f(packDir + QStringLiteral("/styles/") + m_mode + QLatin1Char('-') + m_palette + QStringLiteral(".json"));
    if (!f.open(QIODevice::ReadOnly)) {
        qWarning() << "ChartController: cannot read" << f.fileName();
        return;
    }
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject()) {
        qWarning() << "ChartController: bad style JSON" << f.fileName() << err.errorString();
        return;
    }
    auto style = rewriteStyle(doc.object(), packDir, m_charts->dir, m_bathy ? m_bathy->dir : QString());
    if (!style) {
        qWarning() << "ChartController: cannot use" << f.fileName() << style.error();
        return;
    }
    m_style = *style;
    const QString notice = m_style[QStringLiteral("metadata")][QStringLiteral("cheekymarine")]
                               [QStringLiteral("notice")].toString();
    if (notice != m_notice) {
        m_notice = notice;
        emit noticeChanged();
    }
    // State is set before the call: styleLoaded may arrive inside it.
    m_ready = false;
    m_loadPending = true;
    m_map.setStyleJson(QJsonDocument(m_style).toJson(QJsonDocument::Compact));
}

void ChartController::onStyleLoaded() {
    if (!m_loadPending) return; // one set of runtime additions per load
    m_loadPending = false;
    for (auto it = m_images.cbegin(); it != m_images.cend(); ++it) m_map.addImage(it.key(), it.value());
    m_map.setGeoJson(OverlayIds::kTracksSource, tracksGeoJson(m_tracks));
    m_map.setGeoJson(OverlayIds::kAisSource, aisGeoJson(m_ais.targets(), m_vessel.state()));
    m_map.setGeoJson(OverlayIds::kOwnSource, ownShipGeoJson(m_vessel.state()));
    for (const QJsonObject& layer : runtimeLayers(overlayColours(m_palette))) m_map.addLayer(layer);
    m_ready = true;
    applyDepthFilters();
}

void ChartController::applyDepthFilters() {
    if (!m_ready || !m_charts) return;
    const Depths d{m_settings.shallowM(), m_settings.safetyM(), m_settings.deepM()};
    auto filters = depthFilters(m_style, d, safetyContour(m_charts->valdco, d.safetyM));
    if (!filters) {
        qWarning() << "ChartController: depth filters not applied:" << filters.error();
        return;
    }
    for (auto it = filters->cbegin(); it != filters->cend(); ++it) m_map.setLayerFilter(it.key(), it.value());
}

void ChartController::onVessel() {
    const VesselState& s = m_vessel.state();
    const bool noPos = !s.lat || !s.lon;
    if (noPos != m_noPosition) {
        m_noPosition = noPos;
        emit noPositionChanged();
    }
    if (m_ready) m_map.setGeoJson(OverlayIds::kOwnSource, ownShipGeoJson(s));
    applyCamera();
}

void ChartController::pushAis() {
    if (m_ready) m_map.setGeoJson(OverlayIds::kAisSource, aisGeoJson(m_ais.targets(), m_vessel.state()));
}

void ChartController::applyCamera() {
    const VesselState& s = m_vessel.state();
    if (!m_follow || !s.lat || !s.lon) return;
    const LatLon pos{*s.lat, *s.lon};
    const double zoom = std::clamp(m_map.zoom(), m_minZoom, m_maxZoom);
    const QString o = orientation();
    if (o == QLatin1String("north")) {
        m_map.setCamera(pos.lat, pos.lon, zoom, 0);
        return;
    }
    double bearing = 0;
    if (o == QLatin1String("course")) bearing = cogDeg(s).or_else([&] { return trueHeadingDeg(s); }).value_or(0);
    else bearing = trueHeadingDeg(s).or_else([&] { return cogDeg(s); }).value_or(0);
    // Boat in the lower third: the centre is a sixth of the viewport height ahead of it.
    const LatLon c = destination(pos, bearing, m_map.viewportHeight() / 6 * metresPerPixel(pos.lat, zoom));
    m_map.setCamera(c.lat, c.lon, zoom, bearing);
}
