#include "core/ChartController.h"
#include "core/AisModel.h"
#include "core/Fields.h"
#include "core/Legend.h"
#include "core/DepthFilters.h"
#include "core/Overlays.h"
#include "core/PackMerge.h"
#include "core/Settings.h"
#include "core/StyleLoader.h"
#include "core/Tracks.h"
#include "core/VesselModel.h"
#include <QDebug>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QSet>
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <algorithm>
#include <cmath>

namespace {
constexpr double kStartZoom = 13;
constexpr double kOverzoom = 2;
constexpr double kFallbackMinZoom = 0, kFallbackMaxZoom = 22; // pack without zoom metadata

QJsonObject parse(const char* json) { return QJsonDocument::fromJson(json).object(); }

// A line layer with its paint line-color set.
QJsonObject line(QJsonObject layer, const QColor& colour) {
    QJsonObject paint = layer[QStringLiteral("paint")].toObject();
    paint[QStringLiteral("line-color")] = colour.name();
    layer[QStringLiteral("paint")] = paint;
    return layer;
}

// Track line-dasharray for a line type; null (solid) means no dash.
QJsonValue trackDash(const QString& type) {
    if (type == QLatin1String("dashed")) return QJsonArray{4, 2};
    if (type == QLatin1String("dotted")) return QJsonArray{0.1, 2};
    if (type == QLatin1String("dashdot")) return QJsonArray{4, 2, 0.1, 2};
    return QJsonValue::Null;
}

// Dots need round caps to show; dashes and solid lines keep butt caps.
QString trackCap(const QString& type) {
    return type == QLatin1String("dotted") || type == QLatin1String("dashdot") ? QStringLiteral("round")
                                                                               : QStringLiteral("butt");
}

// A track line layer in `colour` with the dash and cap of `type`.
QJsonObject trackLayer(const char* json, const QColor& colour, const QString& type) {
    QJsonObject layer = line(parse(json), colour);
    QJsonObject paint = layer[QStringLiteral("paint")].toObject();
    if (const QJsonValue dash = trackDash(type); !dash.isNull()) paint[QStringLiteral("line-dasharray")] = dash;
    // No dash transition: MapLibre holds the prior dash for the whole transition, builds the line
    // from it, and does not rebuild when the transition ends (the old dash, or no line for solid).
    // Delay too, so a root style transition delay cannot bring the stale window back.
    paint[QStringLiteral("line-dasharray-transition")] =
        QJsonObject{{QStringLiteral("duration"), 0}, {QStringLiteral("delay"), 0}};
    layer[QStringLiteral("paint")] = paint;
    QJsonObject layout = layer[QStringLiteral("layout")].toObject();
    layout[QStringLiteral("line-cap")] = trackCap(type);
    layer[QStringLiteral("layout")] = layout;
    return layer;
}

// Runtime layers, bottom first: tracks, active track, AIS, own ship (topmost), in the palette's overlay
// colours; the track layers take `trackColor` (night overrides it) and `trackType`.
QList<QJsonObject> runtimeLayers(const OverlayColours& c, const QColor& trackColor, const QString& trackType) {
    return {
        trackLayer(R"({"id":"cm-tracks-line","type":"line","source":"cm-tracks",
            "filter":["==",["get","kind"],"track"],
            "layout":{"line-join":"round"},
            "paint":{"line-width":2.5}})", trackColor, trackType),
        trackLayer(R"({"id":"cm-track-active-line","type":"line","source":"cm-track-active",
            "filter":["==",["get","kind"],"track"],
            "layout":{"line-join":"round"},
            "paint":{"line-width":2.5}})", trackColor, trackType),
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
        parse(R"({"id":"cm-own-cog-tip","type":"symbol","source":"cm-own",
            "filter":["==",["get","kind"],"cogtip"],
            "layout":{"icon-image":"cm-cog-tip","icon-rotate":["get","rot"],
                      "icon-rotation-alignment":"map",
                      "icon-allow-overlap":true,"icon-ignore-placement":true}})"),
        parse(R"({"id":"cm-own-boat","type":"symbol","source":"cm-own",
            "filter":["==",["get","kind"],"boat"],
            "layout":{"icon-image":"cm-boat","icon-rotate":["get","rot"],
                      "icon-rotation-alignment":"map",
                      "icon-allow-overlap":true,"icon-ignore-placement":true}})"),
    };
}

QString styleName(const QString& mode, const QString& palette) { return mode + QLatin1Char('-') + palette; }

// The `mode` ("nav" or "fish") style for `palette`, read from `packDir` (the newest bathy pack for
// fish, the newest charts pack for nav) and rewritten to read the tile files in `sourceFiles`.
std::expected<QJsonObject, QString> readStyle(const QString& mode, const QString& palette, const QString& packDir,
                                              const QHash<QString, QString>& sourceFiles) {
    QFile f(packDir + QStringLiteral("/styles/") + styleName(mode, palette) + QStringLiteral(".json"));
    if (!f.open(QIODevice::ReadOnly)) return std::unexpected(QStringLiteral("cannot be read"));
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject())
        return std::unexpected(QStringLiteral("bad JSON: ") + err.errorString());
    return rewriteStyle(doc.object(), packDir, sourceFiles);
}

// The day, dusk and night `mode` styles of `packDir`, keyed by styleName, each read, rewritten and
// checked to take the depth filters; or why they cannot be used. The error is the same for any depths.
std::expected<QHash<QString, QJsonObject>, QString> readStyles(const QString& mode, const QString& packDir,
                                                               const QHash<QString, QString>& sourceFiles,
                                                               const QList<double>& valdco, const Depths& depths) {
    QHash<QString, QJsonObject> styles;
    for (const QString& palette : {QStringLiteral("day"), QStringLiteral("dusk"), QStringLiteral("night")}) {
        const QString name = styleName(mode, palette);
        QString error;
        if (auto style = readStyle(mode, palette, packDir, sourceFiles)) {
            if (auto filters = depthFilters(*style, depths, safetyContour(valdco, depths.safetyM)); !filters)
                error = filters.error();
            else
                styles.insert(name, *style);
        } else {
            error = style.error();
        }
        if (!error.isEmpty())
            return std::unexpected(QStringLiteral("styles/") + name + QStringLiteral(".json: ") + error);
    }
    return styles;
}

// The newest pack: highest version, then first region name. `usable` is not empty.
const PackInfo& newestOf(const QList<PackInfo>& usable) {
    const PackInfo* best = &usable.first();
    for (const PackInfo& p : usable)
        if (p.version > best->version || (p.version == best->version && p.region < best->region)) best = &p;
    return *best;
}

// Which files a kind shows (spec 5.4a).
enum class Mode { Single, Merged, MergedStale, SingleFallback };

QString modeName(Mode m) {
    switch (m) {
    case Mode::Single: return QStringLiteral("single");
    case Mode::Merged: return QStringLiteral("merged");
    case Mode::MergedStale: return QStringLiteral("merged-stale");
    case Mode::SingleFallback: return QStringLiteral("single-fallback");
    }
    return {};
}

// The tile files one pack kind's styles read, by source name, what is shown, and why.
struct KindFiles {
    QHash<QString, QString> files;
    QList<PackInfo> inUse;             // the merged members, or the one single pack
    std::optional<PackInfo> stylePack; // styles, sprites and glyphs; none without a usable pack
    Mode mode = Mode::Single;
    QStringList notices;
};

// The members of the merged files in `mergedDir` when they are valid: every file is present, opens,
// has its metadata, names members of `kind` in one list, and has a schema the plotter accepts.
std::optional<QList<MergeMember>> validMembers(const QString& mergedDir, const QString& kind, const QStringList& fileNames) {
    std::optional<QList<MergeMember>> out;
    for (const QString& f : fileNames) {
        const QString path = mergedDir + QLatin1Char('/') + f;
        const QList<MergeMember> members = mergeMembers(path);
        const std::optional<int> schema = mergeSchema(path);
        if (members.isEmpty() || !schema || *schema < PLOTTER_PACK_SCHEMA_MIN || *schema > PLOTTER_PACK_SCHEMA_MAX
            || (out && *out != members))
            return std::nullopt;
        for (const MergeMember& m : members)
            if (packDirRe().match(m.dir).captured(1) != kind) return std::nullopt;
        out = members;
    }
    return out;
}

// One usable pack: its own files. Several: the merged files in <packsDir>/merged/<kind>/ when they
// are valid, with a notice line per difference from the usable packs; else the newest single pack's
// (never a mix) with a notice that other areas are blank. `all` is every pack, refused ones too.
KindFiles kindFiles(const QList<PackInfo>& all, const QString& kind, const QStringList& fileNames,
                    const QString& packsDir) {
    KindFiles k;
    const QList<PackInfo> usable = PackCatalog::usable(all, kind);
    if (usable.isEmpty()) return k;
    const bool charts = kind == QLatin1String("charts");
    const QString label = charts ? QStringLiteral("Charts: ") : QStringLiteral("Bathy: ");
    const QString again = QStringLiteral(" Run sudo cheekymarine install again.");
    const QString mergedDir = packsDir + QStringLiteral("/merged/") + kind;
    const auto name = [](const PackInfo& p) { return QFileInfo(p.dir).fileName(); };
    const auto refusedNotices = [&](const QStringList& memberDirs) {
        for (const PackInfo& p : all)
            if (p.kind == kind && !p.refused.isEmpty() && !memberDirs.contains(name(p)))
                k.notices << label + p.region + QLatin1Char(' ') + p.version.toString() + QStringLiteral(" was refused (")
                                 + p.refused + QStringLiteral("). Remove it or install a newer set.");
    };
    const std::optional<QList<MergeMember>> members =
        usable.size() > 1 ? validMembers(mergedDir, kind, fileNames) : std::nullopt;
    if (!members) {
        const PackInfo& newest = newestOf(usable);
        k.mode = usable.size() > 1 ? Mode::SingleFallback : Mode::Single;
        if (k.mode == Mode::SingleFallback) {
            k.notices << label + QStringLiteral("merged files are missing or damaged. Showing ") + newest.region
                             + QStringLiteral(" only; other areas ")
                             + (charts ? QStringLiteral("are blank.") : QStringLiteral("have no depth.")) + again;
            refusedNotices({});
        }
        k.inUse = {newest};
        k.stylePack = newest;
        for (const QString& f : fileNames) k.files.insert(f.chopped(8), newest.dir + QLatin1Char('/') + f); // ".mbtiles"
        return k;
    }
    QStringList memberDirs, memberRegions;
    QList<PackInfo> stylePacks; // members still on disk and not refused
    for (const MergeMember& m : *members) {
        const QRegularExpressionMatch match = packDirRe().match(m.dir);
        const QString region = match.captured(2);
        const QString version = match.captured(3);
        memberDirs << m.dir;
        memberRegions << region;
        const auto disk = std::find_if(all.begin(), all.end(), [&](const PackInfo& p) { return p.kind == kind && name(p) == m.dir; });
        if (disk != all.end()) {
            k.inUse << *disk;
            if (disk->refused.isEmpty()) stylePacks << *disk;
        } else {
            PackInfo gone;
            gone.kind = kind;
            gone.region = region;
            gone.version = QVersionNumber::fromString(version);
            gone.dir = packsDir + QLatin1Char('/') + m.dir;
            gone.onDisk = false;
            k.inUse << gone;
        }
        // A member with no usable pack of its region (gone or refused) is shown, not flagged.
        const auto u = std::find_if(usable.begin(), usable.end(), [&](const PackInfo& p) { return p.region == region; });
        if (u == usable.end()) continue;
        if (name(*u) != m.dir)
            k.notices << label + region + QStringLiteral(" shows ") + version + QStringLiteral(", ") + u->version.toString()
                             + QStringLiteral(" is installed.") + again;
        else if (manifestSha256(u->dir) != m.manifestSha256)
            k.notices << label + region + QLatin1Char(' ') + version + QStringLiteral(" changed after it was merged.") + again;
    }
    for (const PackInfo& u : usable)
        if (!memberRegions.contains(u.region))
            k.notices << label + u.region + QStringLiteral(" is installed but not merged, so it is not shown.") + again;
    refusedNotices(memberDirs);
    k.mode = k.notices.isEmpty() ? Mode::Merged : Mode::MergedStale;
    k.stylePack = newestOf(stylePacks.isEmpty() ? usable : stylePacks);
    for (const QString& f : fileNames) k.files.insert(f.chopped(8), mergedDir + QLatin1Char('/') + f);
    return k;
}
} // namespace

ChartController::ChartController(ChartMap& map, Settings& settings, VesselModel& vessel, AisModel& ais,
                                 QList<PackInfo> packs, const QString& packsDir, QObject* parent)
    : QObject(parent), m_map(map), m_settings(settings), m_vessel(vessel), m_ais(ais), m_packs(std::move(packs)),
      m_packsDir(packsDir) {
    // A pack whose styles cannot be used is refused, with the reason, and the next best one is tried.
    const Depths depths = currentDepths();
    const auto refuse = [this](const QString& dir, const QString& reason) {
        for (PackInfo& p : m_packs)
            if (p.dir == dir) p.refused = reason;
    };
    QList<PackInfo> charts;
    KindFiles cf, bf;
    // The bathy styles are picked for each charts candidate first: nav styles load with them too.
    for (;;) {
        charts = PackCatalog::usable(m_packs, u"charts");
        if (charts.isEmpty()) break;
        cf = kindFiles(m_packs, QStringLiteral("charts"), kChartsFiles, m_packsDir);
        m_charts = cf.stylePack;
        // The contours of the charts shown: the merged file's valdco (the union over all its members, gone
        // ones too), or the single pack's.
        m_valdco = cf.mode == Mode::Merged || cf.mode == Mode::MergedStale
                       ? mergeValdco(m_packsDir + QStringLiteral("/merged/charts/enc.mbtiles"))
                       : cf.inUse.first().valdco;
        const auto withFiles = [&cf](const KindFiles& bathy) {
            QHash<QString, QString> files = cf.files;
            files.insert(bathy.files);
            return files;
        };
        for (;;) {
            bf = kindFiles(m_packs, QStringLiteral("bathy"), kBathyFiles, m_packsDir);
            m_bathy = bf.stylePack;
            if (!m_bathy) break;
            auto fish = readStyles(QStringLiteral("fish"), m_bathy->dir, withFiles(bf), m_valdco, depths);
            if (fish) {
                m_styles.insert(*fish);
                break;
            }
            refuse(m_bathy->dir, fish.error());
        }
        auto nav = readStyles(QStringLiteral("nav"), m_charts->dir, withFiles(bf), m_valdco, depths);
        if (nav) {
            m_styles.insert(*nav);
            break;
        }
        m_styles.clear(); // the refused charts pack's fish styles
        refuse(m_charts->dir, nav.error());
    }
    if (!charts.isEmpty()) {
        m_inUse = cf.inUse + bf.inUse;
        m_packNotices = cf.notices + bf.notices;
        m_packModes.insert(QStringLiteral("charts"), modeName(cf.mode));
        if (m_bathy) m_packModes.insert(QStringLiteral("bathy"), modeName(bf.mode));
        for (const QString& line : m_packNotices) qWarning().noquote() << "ChartController:" << line;
        // The legend of the charts shown: legend.json is not merged, so a gone member adds nothing.
        QSet<QPair<QString, QString>> seen;
        int minZ = -1, maxZ = -1;
        for (const PackInfo& c : cf.inUse)
            for (const LegendEntry& e : c.legend)
                if (!seen.contains({e.abbr, e.kind})) {
                    seen.insert({e.abbr, e.kind});
                    m_legend.append(QVariantMap{{QStringLiteral("abbr"), e.abbr},
                                                {QStringLiteral("meaning"), e.meaning},
                                                {QStringLiteral("kind"), e.kind}});
                }
        // The zoom range is the union over every usable charts pack, shown or not.
        for (const PackInfo& c : charts) {
            if (c.minZoom >= 0) minZ = minZ < 0 ? c.minZoom : std::min(minZ, c.minZoom);
            if (c.maxZoom >= 0) maxZ = std::max(maxZ, c.maxZoom);
        }
        m_minZoom = minZ >= 0 ? minZ : kFallbackMinZoom;
        m_maxZoom = maxZ >= 0 ? maxZ + kOverzoom : kFallbackMaxZoom;
    } else {
        m_charts.reset();
        m_bathy.reset(); // the last refused charts pack's
        m_styles.clear();
        qWarning() << "ChartController: no usable charts pack";
    }
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
    for (auto signal : {&Settings::showHeadingLineChanged, &Settings::showCogLineChanged, &Settings::cogLineMinChanged})
        connect(&m_settings, signal, this, &ChartController::pushOwnShip);
    connect(&m_settings, &Settings::trackColorChanged, this, &ChartController::applyTrackStyle);
    connect(&m_settings, &Settings::trackLineTypeChanged, this, &ChartController::applyTrackStyle);
    connect(&m_vessel, &VesselModel::changed, this, &ChartController::onVessel);
    connect(&m_ais, &QAbstractItemModel::modelReset, this, &ChartController::pushAis);

    m_map.setZoom(std::clamp(kStartZoom, m_minZoom, m_maxZoom));
    rebuildLegend(); // AIS only: without a pack loadStyle returns early
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

void ChartController::setActiveTrack(const QList<LatLon>& points) {
    m_activeTrack = points;
    if (!m_ready) return;
    QElapsedTimer timer;
    if (m_writeTiming) timer.start();
    m_map.setGeoJson(OverlayIds::kActiveTrackSource, tracksGeoJson({m_seedTrack + m_activeTrack}));
    if (m_writeTiming) m_writeTimesUs.append(timer.nsecsElapsed() / 1000);
}

void bindTracks(ChartController& chart, TracksController& tracks) {
    QObject::connect(&tracks, &TracksController::finishedChanged, &chart,
                     [&chart, &tracks] { chart.setTracks(tracks.finished()); });
    QObject::connect(&tracks, &TracksController::activeChanged, &chart,
                     [&chart, &tracks] { chart.setActiveTrack(tracks.active()); });
    chart.setTracks(tracks.finished());
    chart.setActiveTrack(tracks.active());
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

void ChartController::rebuildLegend() {
    m_legendCategories = ::legendCategories(m_mode, m_style, m_palette, m_legend);
    m_spriteBase = m_style[QStringLiteral("sprite")].toString();
    if (m_spriteBase.startsWith(QLatin1String("file://"))) m_spriteBase.remove(0, 7);
    emit legendCategoriesChanged();
}

void ChartController::loadStyle() {
    if (!m_charts) return;
    // Parsed once at start: files that change afterwards are not read again.
    const QString name = styleName(m_mode, m_palette);
    if (!m_styles.contains(name)) {
        qWarning() << "ChartController: no parsed style for" << name;
        return;
    }
    m_style = m_styles.value(name);
    rebuildLegend();
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
    m_map.setGeoJson(OverlayIds::kActiveTrackSource, tracksGeoJson({m_seedTrack + m_activeTrack}));
    m_map.setGeoJson(OverlayIds::kAisSource, aisGeoJson(m_ais.targets(), m_vessel.state()));
    m_map.setGeoJson(OverlayIds::kOwnSource, ownShipGeoJson(m_vessel.state(), ownShipOptions()));
    for (const QJsonObject& layer : runtimeLayers(overlayColours(m_palette),
                                                         trackColour(QColor(m_settings.trackColor()), m_palette),
                                                         m_settings.trackLineType())) m_map.addLayer(layer);
    m_ready = true;
    applyDepthFilters();
    applyCamera();
}

void ChartController::setStartPosition(double lat, double lon) {
    m_startPosition = LatLon{lat, lon};
    applyCamera();
}

void ChartController::applyDepthFilters() {
    if (!m_ready || !m_charts) return;
    const Depths d = currentDepths();
    auto filters = depthFilters(m_style, d, safetyContour(m_valdco, d.safetyM));
    if (!filters) { // the pack was checked at start; its files changed since
        qWarning() << "ChartController: depth filters not applied:" << filters.error();
        return;
    }
    for (auto it = filters->cbegin(); it != filters->cend(); ++it) m_map.setLayerFilter(it.key(), it.value());
}

Depths ChartController::currentDepths() const {
    return {m_settings.shallowM(), m_settings.safetyM(), m_settings.deepM()};
}

void ChartController::onVessel() {
    const VesselState& s = m_vessel.state();
    const bool noPos = !s.lat || !s.lon;
    if (noPos != m_noPosition) {
        m_noPosition = noPos;
        emit noPositionChanged();
    }
    pushOwnShip();
    refreshSelection(); // range and bearing are from the own ship
    applyCamera();
}

OwnShipOptions ChartController::ownShipOptions() const {
    return {m_settings.showHeadingLine(), m_settings.showCogLine(), m_settings.cogLineMin() * 60.0};
}

void ChartController::pushOwnShip() {
    if (m_ready) m_map.setGeoJson(OverlayIds::kOwnSource, ownShipGeoJson(m_vessel.state(), ownShipOptions()));
}

// Track color, dash and cap on the two track layers, now; a reload builds them from the settings.
void ChartController::applyTrackStyle() {
    if (!m_ready) return;
    const QColor colour = trackColour(QColor(m_settings.trackColor()), m_palette);
    const QString type = m_settings.trackLineType();
    for (const QString& layer : {QStringLiteral("cm-tracks-line"), QStringLiteral("cm-track-active-line")}) {
        m_map.setPaintProperty(layer, QStringLiteral("line-color"), colour.name());
        m_map.setPaintProperty(layer, QStringLiteral("line-dasharray"), trackDash(type));
        m_map.setLayoutProperty(layer, QStringLiteral("line-cap"), trackCap(type));
    }
}

void ChartController::pushAis() {
    if (m_ready) m_map.setGeoJson(OverlayIds::kAisSource, aisGeoJson(m_ais.targets(), m_vessel.state()));
    refreshSelection();
}

QVariant ChartController::targetAt(QPointF px, double radiusPx) const {
    QVariant best;
    double bestD = radiusPx;
    for (const AisTarget& t : m_ais.targets()) {
        if (!t.lat || !t.lon) continue;
        const QPointF d = m_map.toScreen(*t.lat, *t.lon) - px;
        const double dist = std::hypot(d.x(), d.y());
        if (dist <= bestD) {
            bestD = dist;
            best = t.mmsi;
        }
    }
    return best;
}

void ChartController::selectAt(QPointF px, double radiusPx) {
    const QVariant hit = targetAt(px, radiusPx);
    if (!hit.isValid()) return;
    m_selectedMmsi = hit.toUInt();
    refreshSelection();
}

void ChartController::clearTarget() {
    m_selectedMmsi = 0;
    refreshSelection();
}

// Rebuilds the sheet's values from the selected target; an unknown MMSI (gone) clears the selection.
void ChartController::refreshSelection() {
    QVariantMap sel;
    if (m_selectedMmsi != 0) {
        const QList<AisTarget> targets = m_ais.targets();
        const auto it = std::find_if(targets.cbegin(), targets.cend(),
                                     [this](const AisTarget& t) { return t.mmsi == m_selectedMmsi; });
        if (it == targets.cend()) {
            m_selectedMmsi = 0;
        } else {
            const AisTarget& t = *it;
            const QString missing = QStringLiteral("--");
            VesselState v; // the target's motion, formatted like the own-ship fields (speed in knots)
            v.sogMs = t.sogMs;
            v.cogRad = t.cogRad;
            UnitPrefs knots;
            knots.speed = SpeedUnit::Knots;
            QString range = missing, bearing = missing;
            const VesselState& own = m_vessel.state();
            if (t.lat && t.lon && own.lat && own.lon) {
                const LatLon from{*own.lat, *own.lon}, to{*t.lat, *t.lon};
                range = QString::number(std::round(distanceM(from, to) / 1852.0 * 10.0) / 10.0, 'f', 1);
                bearing = QStringLiteral("%1").arg(static_cast<int>(std::round(bearingDeg(from, to))) % 360, 3, 10,
                                                   QLatin1Char('0'));
            }
            sel = {{"mmsi", QString::number(t.mmsi)},
                   {"name", t.name.isEmpty() ? QStringLiteral("Unknown") : t.name},
                   {"cls", t.cls.isEmpty() ? missing : t.cls},
                   {"sog", formatValue(Field::Sog, v, knots)},
                   {"cog", formatValue(Field::Cog, v, knots)},
                   {"range", range},
                   {"bearing", bearing},
                   {"posAge", t.posAge ? QStringLiteral("%1 s").arg(static_cast<long long>(std::round(*t.posAge))) : missing}};
        }
    }
    if (sel == m_aisSelection) return;
    m_aisSelection = sel;
    emit aisSelectionChanged();
}

void ChartController::applyCamera() {
    const VesselState& s = m_vessel.state();
    if (!m_follow) return;
    if (!s.lat || !s.lon) {
        if (m_startPosition) m_map.setCamera(m_startPosition->lat, m_startPosition->lon, std::clamp(m_map.zoom(), m_minZoom, m_maxZoom), 0);
        return;
    }
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
