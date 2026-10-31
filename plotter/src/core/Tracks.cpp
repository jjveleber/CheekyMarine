#include "Tracks.h"
#include <QDateTime>
#include <QMetaType>
#include <QSet>
#include <QSqlError>
#include <QSqlQuery>
#include <QVariantMap>
#include <QtLogging>
#include <algorithm>

namespace {

QVariant optionalDouble(const std::optional<double>& v) {
    return v ? QVariant(*v) : QVariant(QMetaType::fromType<double>());
}

} // namespace

qint64 TrackStore::create(double started) {
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("INSERT INTO tracks(name, started, ended, visible) VALUES(?, ?, ?, 1)"));
    q.addBindValue(QDateTime::fromSecsSinceEpoch(qint64(started)).toString(QStringLiteral("yyyy-MM-dd HH:mm")));
    q.addBindValue(started);
    q.addBindValue(started);
    if (!q.exec()) {
        qWarning() << "cannot create a track:" << q.lastError().text();
        return 0;
    }
    return q.lastInsertId().toLongLong();
}

bool TrackStore::append(qint64 id, const QList<TrackPoint>& points, QString* error) {
    if (points.isEmpty())
        return true;
    QSqlDatabase db = m_store.db();
    if (!db.transaction()) {
        if (error)
            *error = db.lastError().text();
        else
            qWarning() << "cannot write track points:" << db.lastError().text();
        return false;
    }
    // The failing statement's own error (QSqlQuery errors are not in db.lastError()).
    QSqlError err;
    QSqlQuery q(db);
    if (!q.prepare(QStringLiteral("INSERT INTO track_points(track_id, t, lat, lon, sog, cog, depth) VALUES(?,?,?,?,?,?,?)")))
        err = q.lastError();
    for (qsizetype i = 0; !err.isValid() && i < points.size(); ++i) {
        const TrackPoint& p = points[i];
        q.addBindValue(id);
        q.addBindValue(p.t);
        q.addBindValue(p.lat);
        q.addBindValue(p.lon);
        q.addBindValue(optionalDouble(p.sog));
        q.addBindValue(optionalDouble(p.cog));
        q.addBindValue(optionalDouble(p.depth));
        if (!q.exec())
            err = q.lastError();
    }
    if (!err.isValid()) {
        QSqlQuery u(db);
        u.prepare(QStringLiteral("UPDATE tracks SET ended = ? WHERE id = ?"));
        u.addBindValue(points.last().t);
        u.addBindValue(id);
        if (!u.exec())
            err = u.lastError();
    }
    if (!err.isValid() && !db.commit())
        err = db.lastError();
    if (err.isValid()) {
        if (error)
            *error = err.text();
        else
            qWarning() << "cannot write track points:" << err.text();
        db.rollback();
        return false;
    }
    const auto it = m_totals.find(id);
    if (it != m_totals.end()) {
        for (const TrackPoint& p : points) {
            const LatLon ll{p.lat, p.lon};
            if (it->points > 0)
                it->distanceM += distanceM(it->last, ll);
            it->last = ll;
            ++it->points;
        }
    }
    return true;
}

QList<TrackInfo> TrackStore::list() {
    QSqlDatabase db = m_store.db();
    QList<TrackInfo> out;
    QSqlQuery q(db);
    if (!q.exec(QStringLiteral("SELECT id, name, started, ended, visible FROM tracks ORDER BY started DESC, id DESC")))
        return out;
    while (q.next()) {
        TrackInfo t;
        t.id = q.value(0).toLongLong();
        t.name = q.value(1).toString();
        t.started = q.value(2).toDouble();
        t.ended = q.value(3).toDouble();
        t.visible = q.value(4).toInt() != 0;
        out.append(t);
    }
    for (TrackInfo& t : out) {
        auto it = m_totals.find(t.id);
        if (it == m_totals.end()) {
            bool ok = false;
            const QList<LatLon> pts = points(t.id, &ok);
            if (!ok) {
                t.points = 0; // read again on the next list()
                continue;
            }
            Totals totals;
            totals.points = int(pts.size());
            for (qsizetype i = 1; i < pts.size(); ++i)
                totals.distanceM += distanceM(pts[i - 1], pts[i]);
            if (!pts.isEmpty())
                totals.last = pts.last();
            it = m_totals.insert(t.id, totals);
        }
        t.points = it->points;
        t.distanceM = it->distanceM;
    }
    return out;
}

QList<LatLon> TrackStore::points(qint64 id, bool* ok) {
    ++m_pointReads;
    QList<LatLon> out;
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("SELECT lat, lon FROM track_points WHERE track_id = ? ORDER BY t, rowid"));
    q.addBindValue(id);
    const bool done = q.exec();
    if (!done)
        qWarning() << "cannot read track points:" << q.lastError().text();
    while (done && q.next())
        out.append({q.value(0).toDouble(), q.value(1).toDouble()});
    if (ok)
        *ok = done;
    return out;
}

void TrackStore::setVisible(qint64 id, bool visible) {
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("UPDATE tracks SET visible = ? WHERE id = ?"));
    q.addBindValue(visible ? 1 : 0);
    q.addBindValue(id);
    if (!q.exec())
        qWarning() << "cannot change a track's visibility:" << q.lastError().text();
}

void TrackStore::remove(qint64 id) {
    QSqlDatabase db = m_store.db();
    if (!db.transaction())
        return;
    QSqlQuery q(db);
    bool ok = q.prepare(QStringLiteral("DELETE FROM track_points WHERE track_id = ?"));
    q.addBindValue(id);
    ok = ok && q.exec();
    QSqlQuery t(db);
    ok = ok && t.prepare(QStringLiteral("DELETE FROM tracks WHERE id = ?"));
    t.addBindValue(id);
    ok = ok && t.exec();
    if (!ok || !db.commit()) {
        qWarning() << "cannot delete a track:" << db.lastError().text();
        db.rollback();
    }
    m_totals.remove(id); // read again if the track is still there
}

TrackRecorder::TrackRecorder(TrackStore& store, Settings& settings, std::function<double()> nowS, QObject* parent)
    : QObject(parent), m_store(store), m_settings(settings), m_nowS(std::move(nowS)) {
    connect(&m_settings, &Settings::trackRecordingChanged, this, &TrackRecorder::recordingChanged);
}

TrackRecorder::~TrackRecorder() {
    flush();
}

void TrackRecorder::dropUnwritten() {
    if (m_buffer.isEmpty())
        return;
    // The write failed and the track is about to change (these points belong to the old track), or
    // a full batch could not be written.
    qWarning() << "dropping" << m_buffer.size() << "unwritten track points";
    m_buffer.clear();
    m_writeFailing = false;
}

void TrackRecorder::startTrack(double t) {
    flush();
    dropUnwritten();
    m_active = m_store.create(t);
    m_last.reset();
    m_activePoints.clear();
    m_lastWriteS = m_nowS();
}

void TrackRecorder::onVessel(const VesselState& s) {
    if (!m_settings.trackRecording() || !s.lat || !s.lon)
        return;
    // The gap runs from the last update that carried a position, whether or not it was stored.
    const bool gap = m_lastPosT && s.t - *m_lastPosT > kNewTrackGapS;
    m_lastPosT = s.t;
    if (m_active == 0 || gap)
        startTrack(s.t);
    if (m_active == 0)
        return; // the track could not be created

    TrackPoint p;
    p.t = s.t;
    p.lat = *s.lat;
    p.lon = *s.lon;
    p.sog = s.sogMs;
    p.cog = s.cogRad;
    p.depth = s.depthM;
    const bool keep = !m_last || (p.t - m_last->t >= m_settings.trackIntervalS() &&
                                  distanceM({m_last->lat, m_last->lon}, {p.lat, p.lon}) >= m_settings.trackMinDistanceM());
    if (keep) {
        if (m_buffer.isEmpty())
            m_bufferId = m_active;
        m_buffer.append(p);
        m_last = p;
        m_activePoints.append({p.lat, p.lon});
        emit activeTrackChanged(m_activePoints);
    }
    if (m_buffer.size() >= kWriteBatch)
        flush();
    else
        tick();
}

void TrackRecorder::flush() {
    if (m_buffer.isEmpty())
        return;
    m_lastWriteS = m_nowS();
    QString error;
    if (m_store.append(m_bufferId, m_buffer, &error)) {
        m_buffer.clear();
        m_writeFailing = false;
        return;
    }
    // One warning when the buffer first fails and one when it is dropped; the retries between
    // (every 30 s, and at a full batch) are silent.
    if (!m_writeFailing)
        qWarning() << "cannot write track points:" << error;
    m_writeFailing = true;
    if (m_buffer.size() >= kWriteBatch)
        dropUnwritten(); // writes keep failing: hold at most one batch
}

void TrackRecorder::tick() {
    if (!m_buffer.isEmpty() && m_nowS() - m_lastWriteS >= kWriteIntervalS)
        flush();
}

void TrackRecorder::recordingChanged() {
    if (m_settings.trackRecording())
        return;
    flush();
    dropUnwritten();
    m_active = 0;
    m_last.reset();
    m_lastPosT.reset();
    m_activePoints.clear();
    emit activeTrackChanged({});
}

TracksController::TracksController(TrackStore& store, TrackRecorder& recorder, QObject* parent)
    : QObject(parent), m_store(store), m_recorder(recorder) {
    connect(&m_recorder, &TrackRecorder::activeTrackChanged, this, &TracksController::onActive);
    refresh();
}

void TracksController::refresh() {
    const qint64 active = m_recorder.activeId();
    m_shownActive = active;
    QVariantList rows;
    QList<qint64> finishedIds;
    QSet<qint64> finishedAll; // shown or hidden
    for (const TrackInfo& t : m_store.list()) {
        if (t.id != active)
            finishedAll.insert(t.id);
        QVariantMap row;
        row[QStringLiteral("id")] = t.id;
        row[QStringLiteral("name")] = t.name;
        row[QStringLiteral("durationS")] = t.ended - t.started;
        row[QStringLiteral("distanceM")] = t.distanceM;
        row[QStringLiteral("points")] = t.points;
        row[QStringLiteral("visible")] = t.visible;
        row[QStringLiteral("active")] = t.id == active;
        rows.append(row);
        if (t.visible && t.id != active)
            finishedIds.append(t.id);
    }
    if (rows != m_rows) {
        m_rows = rows;
        emit tracksChanged();
    }
    // Finished tracks never change: each one's line is read once and kept while it is a finished
    // track (deleted ones go, so a reused id is read again), and sent only when the set changes.
    // A failed read is not kept: it shows empty and is read again on the next refresh.
    m_lines.removeIf([&finishedAll](const auto& it) { return !finishedAll.contains(it.key()); });
    const bool unread = std::ranges::any_of(finishedIds, [this](qint64 id) { return !m_lines.contains(id); });
    if (finishedIds != m_finishedIds || unread) {
        QList<QList<LatLon>> finished;
        bool read = false; // a line was read now
        for (qint64 id : finishedIds) {
            auto it = m_lines.find(id);
            if (it == m_lines.end()) {
                bool ok = false;
                const QList<LatLon> line = m_store.points(id, &ok);
                if (!ok) {
                    finished.append(QList<LatLon>());
                    continue;
                }
                it = m_lines.insert(id, line);
                read = true;
            }
            finished.append(*it);
        }
        if (finishedIds != m_finishedIds || read) {
            m_finishedIds = finishedIds;
            m_finished = finished;
            emit finishedChanged();
        }
    }
}

void TracksController::setVisible(qint64 id, bool visible) {
    m_store.setVisible(id, visible);
    refresh();
}

void TracksController::remove(qint64 id) {
    if (id == m_recorder.activeId())
        return;
    m_store.remove(id);
    refresh();
}

void TracksController::onActive(const QList<LatLon>& points) {
    m_activePoints = points;
    if (m_recorder.activeId() != m_shownActive)
        refresh(); // a track began or recording stopped: the finished ones change too
    emit activeChanged();
}
