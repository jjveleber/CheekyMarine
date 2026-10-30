#pragma once
#include "core/ChartMap.h"
#include "core/Geo.h"
#include "core/PackCatalog.h"
#include <QHash>
#include <QImage>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QVariantList>
#include <optional>

class Settings;
class VesselModel;
class AisModel;

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
    // The charts pack's legend: list of {abbr, meaning, kind}; empty without a pack or legend.json.
    Q_PROPERTY(QVariantList legend READ legend CONSTANT)
    Q_PROPERTY(bool noPosition READ noPosition NOTIFY noPositionChanged)
    Q_PROPERTY(double minZoom READ minZoom CONSTANT)
    Q_PROPERTY(double maxZoom READ maxZoom CONSTANT)
    // The AIS target shown on the AisSheet: strings {mmsi, name, cls, sog, cog, range, bearing, posAge}
    // ("--" for a missing value); empty when none is selected. Follows the target as it moves and
    // is cleared when it disappears.
    Q_PROPERTY(QVariantMap aisSelection READ aisSelection NOTIFY aisSelectionChanged)

public:
    // All references must outlive the controller. Loads the style for Settings::chartMode at once.
    ChartController(ChartMap& map, Settings& settings, VesselModel& vessel, AisModel& ais, QList<PackInfo> packs,
                    QObject* parent = nullptr);

    QString mode() const { return m_mode; }
    void setMode(const QString& mode); // "nav" or "fish"; "fish" is refused without a bathy pack
    QString orientation() const;
    void setOrientation(const QString& orientation); // writes Settings::orientation
    QString palette() const { return m_palette; }
    void setPalette(const QString& palette); // "day", "dusk" or "night"
    bool follow() const { return m_follow; }
    void setFollow(bool follow);
    bool fishAvailable() const { return m_bathy.has_value(); }
    QString notice() const { return m_notice; }
    QVariantList legend() const { return m_legend; }
    bool noPosition() const { return m_noPosition; }
    double minZoom() const { return m_minZoom; }
    double maxZoom() const { return m_maxZoom; }

    // Runtime images by id (OverlayIds), added now if a style is loaded and after every load.
    void setImages(const QHash<QString, QImage>& images);
    void setTracks(const QList<QList<LatLon>>& tracks);

    // Changes the zoom by `log2Delta` (clamped to minZoom..maxZoom) and, when following, re-applies
    // the camera so the boat keeps its place. Pinch and wheel use it while following.
    Q_INVOKABLE void zoomBy(double log2Delta);
    Q_INVOKABLE void zoomIn();
    Q_INVOKABLE void zoomOut();
    Q_INVOKABLE void recenter();

    // MMSI (as uint) of the nearest AIS target whose screen position is within `radiusPx` of `px`
    // (item pixels); an invalid QVariant when there is none.
    Q_INVOKABLE QVariant targetAt(QPointF px, double radiusPx) const;
    // Selects targetAt(px, radiusPx), or leaves the selection alone on a miss.
    Q_INVOKABLE void selectAt(QPointF px, double radiusPx);
    Q_INVOKABLE void clearTarget();
    QVariantMap aisSelection() const { return m_aisSelection; }

signals:
    void modeChanged();
    void orientationChanged();
    void paletteChanged();
    void followChanged();
    void noticeChanged();
    void noPositionChanged();
    void aisSelectionChanged();

private:
    void loadStyle();
    void onStyleLoaded();
    void applyDepthFilters();
    void onVessel();
    void pushAis();
    void refreshSelection();
    void applyCamera();

    ChartMap& m_map;
    Settings& m_settings;
    VesselModel& m_vessel;
    AisModel& m_ais;
    std::optional<PackInfo> m_charts, m_bathy;
    QString m_mode = QStringLiteral("nav");
    QString m_palette = QStringLiteral("day");
    bool m_follow = true;
    QString m_notice;
    QVariantList m_legend;
    bool m_noPosition = true;
    double m_minZoom = 0, m_maxZoom = 22;
    QJsonObject m_style;       // the style being shown (or loading)
    bool m_loadPending = false; // a setStyleJson whose styleLoaded has not arrived yet
    bool m_ready = false;       // runtime sources and layers are on the map
    QHash<QString, QImage> m_images;
    QList<QList<LatLon>> m_tracks;
    quint32 m_selectedMmsi = 0;
    QVariantMap m_aisSelection;
};
