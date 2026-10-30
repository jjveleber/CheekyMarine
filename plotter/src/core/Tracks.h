#pragma once
#include "Geo.h"
#include "Settings.h"
#include "Store.h"
#include "VesselState.h"
#include <QList>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <functional>
#include <optional>

struct TrackPoint {
    double t = 0, lat = 0, lon = 0;
    std::optional<double> sog, cog, depth;
};

struct TrackInfo {
    qint64 id = 0;
    QString name;
    double started = 0, ended = 0;
    bool visible = true;
    double distanceM = 0;
    int points = 0;
};

// Tracks and their points in the store's tracks and track_points tables.
class TrackStore {
public:
    explicit TrackStore(Store& store) : m_store(store) {}
    // A new visible track named after `started` (epoch seconds) in local time, "yyyy-MM-dd HH:mm".
    qint64 create(double started);
    // Adds the points in one transaction and moves `ended` to the last one's time. False (nothing
    // written) on a database error.
    bool append(qint64 id, const QList<TrackPoint>& points);
    // Newest first. The distance is summed over the stored points.
    QList<TrackInfo> list();
    QList<LatLon> points(qint64 id);
    void setVisible(qint64 id, bool visible);
    void remove(qint64 id);

private:
    Store& m_store;
};

// Turns vessel updates into stored track points (rules in the plotter spec, 6.13).
class TrackRecorder : public QObject {
    Q_OBJECT
public:
    static constexpr double kNewTrackGapS = 600;
    static constexpr double kWriteIntervalS = 30;
    static constexpr int kWriteBatch = 20;

    // nowS: the wall clock in seconds, for the write interval only; point times come from the vessel.
    TrackRecorder(TrackStore& store, Settings& settings, std::function<double()> nowS, QObject* parent = nullptr);
    ~TrackRecorder() override;

    void onVessel(const VesselState& s);
    // Writes the buffered points now.
    void flush();
    // Writes the buffer when 30 s have passed since the last write (a timer calls it, so a quiet
    // data feed does not leave points unwritten).
    void tick();
    // 0 when no track is active (not recording, or no position yet).
    qint64 activeId() const { return m_active; }

signals:
    // The whole active track, written and buffered points.
    void activeTrackChanged(const QList<LatLon>& points);

private:
    void recordingChanged();
    void startTrack(double t);

    TrackStore& m_store;
    Settings& m_settings;
    std::function<double()> m_nowS;
    qint64 m_active = 0;
    QList<TrackPoint> m_buffer;
    QList<LatLon> m_activePoints;
    std::optional<TrackPoint> m_last; // last stored point of the active track
    std::optional<double> m_lastPosT; // last vessel update that carried a position, stored or not
    double m_lastWriteS = 0;
};

// What the tracks page and the chart see: rows with show/hide and delete, and the lines to draw
// (the active track always, the others when visible).
class TracksController : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList tracks READ tracks NOTIFY tracksChanged)
public:
    TracksController(TrackStore& store, TrackRecorder& recorder, QObject* parent = nullptr);

    QVariantList tracks() const { return m_rows; }
    QList<QList<LatLon>> shown() const;

    // Reloads the rows (the active track's counts include only written points).
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void setVisible(qint64 id, bool visible);
    // The active track cannot be deleted.
    Q_INVOKABLE void remove(qint64 id);

signals:
    void tracksChanged();
    void shownChanged();

private:
    void onActive(const QList<LatLon>& points);

    TrackStore& m_store;
    TrackRecorder& m_recorder;
    QVariantList m_rows;
    QList<QList<LatLon>> m_others; // visible tracks other than the active one
    QList<LatLon> m_activePoints;
    qint64 m_shownActive = 0;
};
