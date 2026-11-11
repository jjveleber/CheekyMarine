#pragma once
#include "core/ChartMap.h"
#include "core/Geo.h"
#include "core/PackCatalog.h"
#include <QHash>
#include <QImage>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>
#include <optional>

struct Depths;
struct OwnShipOptions;
class Settings;
class VesselModel;
class AisModel;
class TracksController;

// Chart page logic: picks and loads the style, keeps the runtime overlays (tracks, AIS, own ship)
// and depth filters on the map across style reloads, and drives the follow camera.
class ChartController : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString mode READ mode WRITE setMode NOTIFY modeChanged)
    Q_PROPERTY(QString orientation READ orientation WRITE setOrientation NOTIFY orientationChanged)
    Q_PROPERTY(QString palette READ palette WRITE setPalette NOTIFY paletteChanged)
    Q_PROPERTY(bool follow READ follow WRITE setFollow NOTIFY followChanged)
    Q_PROPERTY(bool fishAvailable READ fishAvailable CONSTANT)
    Q_PROPERTY(QString notice READ notice NOTIFY noticeChanged)
    // One line per difference between the installed packs and the files shown (spec 5.4a): merged
    // files kept although packs differ, or a single pack shown because the merged files are missing
    // or damaged. Empty after a normal install. Unlike `notice`, a style load never changes it.
    Q_PROPERTY(QStringList packNotices READ packNotices CONSTANT)
    // Per kind with a pack shown ("charts", "bathy"): "single", "merged", "merged-stale" (merged
    // files kept, packs differ) or "single-fallback" (merged files missing or damaged).
    Q_PROPERTY(QVariantMap packModes READ packModes CONSTANT)
    // The charts pack's legend: list of {abbr, meaning, kind}; empty without a pack or legend.json.
    Q_PROPERTY(QVariantList legend READ legend CONSTANT)
    // The legend for the current view (legendCategories() in Legend.h): AIS only without a pack,
    // rebuilt on every style load.
    Q_PROPERTY(QVariantList legendCategories READ legendCategories NOTIFY legendCategoriesChanged)
    // The loaded style's sprite path without "file://" (no .json or .png suffix); empty without a style.
    Q_PROPERTY(QString spriteBase READ spriteBase NOTIFY legendCategoriesChanged)
    Q_PROPERTY(bool noPosition READ noPosition NOTIFY noPositionChanged)
    Q_PROPERTY(double minZoom READ minZoom CONSTANT)
    Q_PROPERTY(double maxZoom READ maxZoom CONSTANT)
    // The AIS target shown on the AisSheet: strings {mmsi, name, cls, sog, cog, range, bearing, posAge}
    // ("--" for a missing value); empty when none is selected. Follows the target as it moves and
    // is cleared when it disappears.
    Q_PROPERTY(QVariantMap aisSelection READ aisSelection NOTIFY aisSelectionChanged)

public:
    // All references must outlive the controller. Starts in nav and loads its style at once.
    // `packsDir` holds the pack directories and merged/<kind>/ (written by --merge-packs).
    ChartController(ChartMap& map, Settings& settings, VesselModel& vessel, AisModel& ais, QList<PackInfo> packs,
                    const QString& packsDir, QObject* parent = nullptr);

    QString mode() const { return m_mode; }
    void setMode(const QString& mode); // "nav" or "fish"; "fish" is refused without a bathy pack. Not stored.
    QString orientation() const;
    void setOrientation(const QString& orientation); // writes Settings::orientation
    QString palette() const { return m_palette; }
    void setPalette(const QString& palette); // "day", "dusk" or "night"
    bool follow() const { return m_follow; }
    void setFollow(bool follow);
    bool fishAvailable() const { return m_bathy.has_value(); } // any usable bathy pack
    QString notice() const { return m_notice; }
    QStringList packNotices() const { return m_packNotices; }
    QVariantMap packModes() const { return m_packModes; }
    QVariantList legend() const { return m_legend; }
    QVariantList legendCategories() const { return m_legendCategories; }
    QString spriteBase() const { return m_spriteBase; }
    bool noPosition() const { return m_noPosition; }
    double minZoom() const { return m_minZoom; }
    double maxZoom() const { return m_maxZoom; }
    // Every pack given, with `refused` set on a pack whose styles cannot be used (a depth filter error,
    // or a style that cannot be read or rewritten). The About page lists this, not the scan.
    QList<PackInfo> packs() const { return m_packs; }
    // What is shown, charts then bathy: the merged files' members (region and version from the dir
    // name; one whose dir is gone has `onDisk` false), or the one single pack of that kind.
    QList<PackInfo> packsInUse() const { return m_inUse; }

    // The own-ship line switches and COG line length from the settings.
    OwnShipOptions ownShipOptions() const;

    // Runtime images by id (OverlayIds), added now if a style is loaded and after every load.
    void setImages(const QHash<QString, QImage>& images);
    // The finished visible tracks (cm-tracks) and the track being recorded (cm-track-active): a
    // kept point re-sends only the active one.
    void setTracks(const QList<QList<LatLon>>& tracks);
    void setActiveTrack(const QList<LatLon>& points);
    // --seed-track: points written ahead of every active-track write (a measurement aid; the recorder never sees them).
    void setSeedTrack(const QList<LatLon>& prefix) { m_seedTrack = prefix; }
    // --frame-stats: when on, records the main-thread time (us) of each active-track map write.
    void setWriteTiming(bool on) { m_writeTiming = on; }
    QList<qint64> writeTimesUs() const { return m_writeTimesUs; }

    // Changes the zoom by `log2Delta` (clamped to minZoom..maxZoom) and, when following, re-applies
    // the camera so the boat keeps its place. Pinch and wheel use it while following.
    Q_INVOKABLE void zoomBy(double log2Delta);
    Q_INVOKABLE void zoomIn();
    Q_INVOKABLE void zoomOut();
    Q_INVOKABLE void recenter();
    // Dev option --position: where the map centers while the vessel has no position (a fix wins).
    void setStartPosition(double lat, double lon);

    // MMSI (as uint) of the nearest AIS target whose screen position is within `radiusPx` of `px`
    // (item pixels); an invalid QVariant when there is none.
    Q_INVOKABLE QVariant targetAt(QPointF px, double radiusPx) const;
    // Selects targetAt(px, radiusPx), or leaves the selection alone on a miss.
    Q_INVOKABLE void selectAt(QPointF px, double radiusPx);
    Q_INVOKABLE void clearTarget();
    // Selects the target with this MMSI (dev option --sheet ais); a gone MMSI clears the selection.
    void selectMmsi(quint32 mmsi) { m_selectedMmsi = mmsi; refreshSelection(); }
    QVariantMap aisSelection() const { return m_aisSelection; }

signals:
    void modeChanged();
    void orientationChanged();
    void paletteChanged();
    void followChanged();
    void noticeChanged();
    void noPositionChanged();
    void aisSelectionChanged();
    void legendCategoriesChanged();

private:
    void loadStyle();
    void rebuildLegend();
    void onStyleLoaded();
    void addImages();
    void applyDepthFilters();
    Depths currentDepths() const;
    void onVessel();
    void pushAis();
    void pushOwnShip();
    void applyTrackStyle();
    void refreshSelection();
    void applyCamera();

    ChartMap& m_map;
    Settings& m_settings;
    VesselModel& m_vessel;
    AisModel& m_ais;
    QList<PackInfo> m_packs;
    QString m_packsDir;
    // Per kind, where styles, sprites and glyphs come from: the newest merged member still on disk,
    // else the newest usable pack.
    std::optional<PackInfo> m_charts, m_bathy;
    QList<double> m_valdco;                    // of the charts shown: the merged file's, or the single pack's
    QList<PackInfo> m_inUse;
    QStringList m_packNotices;
    QVariantMap m_packModes;
    QString m_mode = QStringLiteral("nav");
    QString m_palette = QStringLiteral("day");
    bool m_follow = true;
    std::optional<LatLon> m_startPosition;
    QString m_notice;
    QVariantList m_legend;
    QVariantList m_legendCategories;
    QString m_spriteBase;
    bool m_noPosition = true;
    double m_minZoom = 0, m_maxZoom = 22;
    QHash<QString, QJsonObject> m_styles; // the accepted packs' parsed styles, keyed by style name
    QJsonObject m_style;       // the style being shown (or loading)
    bool m_loadPending = false; // a setStyleJson whose styleLoaded has not arrived yet
    bool m_ready = false;       // runtime sources and layers are on the map
    QHash<QString, QImage> m_images;
    bool m_backgroundAdded = false; // the background fill layer is on the current style
    QList<QList<LatLon>> m_tracks;
    QList<LatLon> m_activeTrack;
    QList<LatLon> m_seedTrack;
    bool m_writeTiming = false;
    QList<qint64> m_writeTimesUs;
    quint32 m_selectedMmsi = 0;
    QVariantMap m_aisSelection;
};

// Draws `tracks` on `chart` now and whenever its finished or active lines change. Both must outlive
// the connections (the app declares them in main).
void bindTracks(ChartController& chart, TracksController& tracks);
