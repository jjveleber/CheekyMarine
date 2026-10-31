#include "core/Tracks.h"
#include <QCoreApplication>
#include <QDateTime>
#include <QProcess>
#include <QSignalSpy>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>
#include <cstdio>

namespace {

constexpr double kLatPerM = 1.0 / 111195.0;

VesselState at(double t, double lat, double lon = -122.23) {
    VesselState s;
    s.t = t;
    s.lat = lat;
    s.lon = lon;
    return s;
}

// A store, settings and recorder on a fake clock that follows the vessel times fed in.
struct Rig {
    QTemporaryDir dir;
    std::unique_ptr<Store> store;
    std::unique_ptr<Settings> settings;
    std::unique_ptr<TrackStore> tracks;
    double now = 1000;
    std::unique_ptr<TrackRecorder> rec;

    explicit Rig(bool recording = true, int interval = 5, double minDist = 10) {
        auto s = Store::open(dir.path());
        if (!s) qFatal("cannot open the store");
        store = std::move(*s);
        settings = std::make_unique<Settings>(*store);
        settings->setTrackRecording(recording);
        settings->setTrackIntervalS(interval);
        settings->setTrackMinDistanceM(minDist);
        tracks = std::make_unique<TrackStore>(*store);
        rec = std::make_unique<TrackRecorder>(*tracks, *settings, [this] { return now; });
    }
    ~Rig() {
        rec.reset();
        tracks.reset();
        settings.reset();
    }
    // Feeds an update at vessel time t (the clock follows).
    void feed(double t, double lat, double lon = -122.23) {
        now = t;
        rec->onVessel(at(t, lat, lon));
    }
    int stored(qint64 id) { return int(tracks->points(id).size()); }
    int rows(const QString& table) {
        QSqlQuery q(store->db());
        if (!q.exec("SELECT count(*) FROM " + table) || !q.next()) return -1;
        return q.value(0).toInt();
    }
};

// Child of the power-cut test: records one point per synthetic second, forever, reporting each
// point it has handed to the recorder on stdout.
int runRecorder(const QString& dir) {
    auto store = Store::open(dir);
    if (!store) return 2;
    Settings settings(**store);
    settings.setTrackRecording(true);
    settings.setTrackIntervalS(1);
    settings.setTrackMinDistanceM(0);
    TrackStore tracks(**store);
    double now = 0;
    TrackRecorder rec(tracks, settings, [&now] { return now; });
    for (int i = 0;; ++i) {
        now = i;
        rec.onVessel(at(1000 + i, 47.0 + i * 1e-4, -122.0));
        std::printf("%d\n", i);
        std::fflush(stdout);
    }
}

} // namespace

class TstTracks : public QObject {
    Q_OBJECT
private slots:
    void recordingOffStoresNothing() {
        Rig r(false);
        for (int i = 0; i < 60; ++i) r.feed(i, 47.98 + i * 3 * kLatPerM);
        r.rec->flush();
        QCOMPARE(r.tracks->list().size(), 0);
        QCOMPARE(r.rows("track_points"), 0);
    }
    void movingBoatStoresOnePointPerInterval() {
        Rig r; // interval 5 s, minimum distance 10 m, 3 m/s: 15 m per interval
        for (int i = 0; i < 60; ++i) r.feed(i, 47.98 + i * 3 * kLatPerM);
        r.rec->flush();
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].points, 12);
        const auto pts = r.tracks->points(l[0].id);
        QCOMPARE(pts.size(), 12);
        QVERIFY(distanceM(pts[0], pts[1]) > 14 && distanceM(pts[0], pts[1]) < 16);
    }
    void stoppedBoatStoresNoNewPoints() {
        Rig r;
        for (int i = 0; i <= 600; ++i) r.feed(i, 47.98);
        r.rec->flush();
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].points, 1);
    }
    void gapOf601SecondsStartsASecondTrack() {
        Rig r;
        r.feed(0, 47.98);
        r.feed(601, 47.99);
        r.rec->flush();
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 2);
        QCOMPARE(l[0].points, 1); // the new one, newest first
        QCOMPARE(l[1].points, 1);
    }
    void gapOf599SecondsKeepsTheTrack() {
        Rig r;
        r.feed(0, 47.98);
        r.feed(599, 47.99);
        r.rec->flush();
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].points, 2);
    }
    // R9: the gap runs from the last update with a position, stored or not.
    void anchoredBoatStillReportingDoesNotSplit() {
        Rig r;
        for (int t = 0; t <= 1500; t += 100) r.feed(t, 47.98);
        r.rec->flush();
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].points, 1);
    }
    void updatesWithoutPositionAreIgnoredAndDoNotResetTheGap() {
        Rig r;
        r.feed(0, 47.98);
        r.now = 300;
        VesselState none;
        none.t = 300;
        r.rec->onVessel(none);
        r.feed(601, 47.99);
        r.rec->flush();
        QCOMPARE(r.tracks->list().size(), 2);
    }
    void nineteenPointsThenThirtyOneSecondsAreWritten() {
        Rig r(true, 1, 10);
        for (int i = 0; i < 19; ++i) r.feed(i, 47.0 + i * 20 * kLatPerM);
        const qint64 id = r.rec->activeId();
        QVERIFY(id != 0);
        QCOMPARE(r.stored(id), 0);
        r.feed(50, 47.0 + 18 * 20 * kLatPerM); // same place: not stored, but 31 s since the last write
        QCOMPARE(r.stored(id), 19);
    }
    void twentyPointsAreWrittenAtOnce() {
        Rig r(true, 1, 10);
        for (int i = 0; i < 20; ++i) r.feed(i, 47.0 + i * 20 * kLatPerM);
        QCOMPARE(r.stored(r.rec->activeId()), 20);
    }
    void nineteenPointsWithinThirtySecondsWaitForFlush() {
        Rig r(true, 1, 10);
        for (int i = 0; i < 19; ++i) r.feed(i, 47.0 + i * 20 * kLatPerM);
        QCOMPARE(r.stored(r.rec->activeId()), 0);
        r.rec->flush();
        QCOMPARE(r.stored(r.rec->activeId()), 19);
    }
    void tickWritesWhenThirtySecondsPassedWithNoData() {
        Rig r(true, 1, 10);
        for (int i = 0; i < 5; ++i) r.feed(i, 47.0 + i * 20 * kLatPerM);
        r.now = 20;
        r.rec->tick();
        QCOMPARE(r.stored(r.rec->activeId()), 0);
        r.now = 31;
        r.rec->tick();
        QCOMPARE(r.stored(r.rec->activeId()), 5);
    }
    void turningRecordingOffFlushes() {
        Rig r;
        for (int i = 0; i < 3; ++i) r.feed(i * 5, 47.0 + i * 20 * kLatPerM);
        const qint64 id = r.rec->activeId();
        QCOMPARE(r.stored(id), 0);
        r.settings->setTrackRecording(false);
        QCOMPARE(r.stored(id), 3);
        QCOMPARE(r.rec->activeId(), qint64(0));
        r.feed(100, 48.0); // off: ignored
        QCOMPARE(r.tracks->list().size(), 1);
    }
    void turningRecordingBackOnStartsANewTrack() {
        Rig r;
        r.feed(0, 47.98);
        r.settings->setTrackRecording(false);
        r.settings->setTrackRecording(true);
        r.feed(10, 47.98);
        r.rec->flush();
        QCOMPARE(r.tracks->list().size(), 2);
    }
    void destructorWritesTheBuffer() {
        Rig r;
        r.feed(0, 47.98);
        const qint64 id = r.rec->activeId();
        r.rec.reset();
        QCOMPARE(r.stored(id), 1);
    }
    void activeTrackSignalCarriesTheWholeTrackIncludingBuffered() {
        Rig r;
        QSignalSpy spy(r.rec.get(), &TrackRecorder::activeTrackChanged);
        r.feed(0, 47.98);
        r.feed(5, 48.0);
        QCOMPARE(spy.size(), 2);
        QCOMPARE(spy.last().at(0).value<QList<LatLon>>().size(), 2);
        r.feed(6, 48.0); // not stored: no signal
        QCOMPARE(spy.size(), 2);
    }
    void listDistanceMatchesGeo() {
        Rig r;
        const qint64 id = r.tracks->create(1000);
        TrackPoint a, b;
        a.t = 1000; a.lat = 47.98; a.lon = -122.23;
        b.t = 1010; b.lat = 47.99; b.lon = -122.23;
        QVERIFY(r.tracks->append(id, {a, b}));
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 1);
        QVERIFY(std::abs(l[0].distanceM - distanceM({47.98, -122.23}, {47.99, -122.23})) <= 0.01);
        QCOMPARE(l[0].points, 2);
        QCOMPARE(l[0].started, 1000.0);
        QCOMPARE(l[0].ended, 1010.0);
    }
    // list() keeps each track's distance and point count; appends extend them, and the totals
    // still equal the sum over the stored points.
    void listDistanceStaysTheSumAfterAppends() {
        Rig r;
        const qint64 id = r.tracks->create(1000), other = r.tracks->create(900);
        auto pt = [](double t, double lat) {
            TrackPoint p;
            p.t = t; p.lat = lat; p.lon = -122.23;
            return p;
        };
        QVERIFY(r.tracks->append(id, {pt(1000, 47.98), pt(1010, 47.99)}));
        QVERIFY(r.tracks->append(other, {pt(900, 47.0), pt(901, 47.01)}));
        QCOMPARE(r.tracks->list()[0].points, 2);
        QVERIFY(r.tracks->append(id, {pt(1020, 48.0), pt(1030, 48.02)}));
        QVERIFY(r.tracks->append(id, {pt(1040, 48.03)}));
        const auto l = r.tracks->list();
        QCOMPARE(l[0].id, id);
        const QList<LatLon> pts = r.tracks->points(id);
        double sum = 0;
        for (qsizetype i = 1; i < pts.size(); ++i) sum += distanceM(pts[i - 1], pts[i]);
        QCOMPARE(l[0].points, 5);
        QVERIFY(std::abs(l[0].distanceM - sum) <= 1e-6);
        QCOMPARE(l[0].ended, 1040.0);
        QVERIFY(std::abs(l[1].distanceM - distanceM({47.0, -122.23}, {47.01, -122.23})) <= 1e-6);
        QCOMPARE(l[1].points, 2);
    }
    // list() does not reload the points of tracks it has seen: with the points table gone it still
    // reports the stored totals.
    void listDoesNotReloadPoints() {
        Rig r;
        const qint64 id = r.tracks->create(1000);
        TrackPoint a, b;
        a.t = 1000; a.lat = 47.98; a.lon = -122.23;
        b.t = 1010; b.lat = 47.99; b.lon = -122.23;
        QVERIFY(r.tracks->append(id, {a, b}));
        const double d = r.tracks->list()[0].distanceM;
        QVERIFY(d > 1000);
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("ALTER TABLE track_points RENAME TO track_points_off"));
        const auto l = r.tracks->list();
        QVERIFY(q.exec("ALTER TABLE track_points_off RENAME TO track_points"));
        QCOMPARE(l[0].points, 2);
        QCOMPARE(l[0].distanceM, d);
    }
    void createNamesTheTrackInLocalTimeAndListsNewestFirst() {
        Rig r;
        const double t1 = 1.7e9, t2 = 1.7e9 + 86400;
        const qint64 a = r.tracks->create(t1), b = r.tracks->create(t2);
        const auto l = r.tracks->list();
        QCOMPARE(l.size(), 2);
        QCOMPARE(l[0].id, b);
        QCOMPARE(l[1].id, a);
        QCOMPARE(l[0].name, QDateTime::fromSecsSinceEpoch(qint64(t2)).toString("yyyy-MM-dd HH:mm"));
        QVERIFY(l[0].visible);
    }
    void appendKeepsOptionalValuesNull() {
        Rig r;
        const qint64 id = r.tracks->create(0);
        TrackPoint a;
        a.t = 1; a.lat = 1; a.lon = 2; a.sog = 3.5;
        QVERIFY(r.tracks->append(id, {a}));
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("SELECT sog, cog, depth FROM track_points"));
        QVERIFY(q.next());
        QCOMPARE(q.value(0).toDouble(), 3.5);
        QVERIFY(q.value(1).isNull());
        QVERIFY(q.value(2).isNull());
    }
    void recorderStoresSogCogDepth() {
        Rig r;
        VesselState s = at(0, 47.98);
        s.sogMs = 2.0;
        s.cogRad = 1.0;
        s.depthM = 12.5;
        r.rec->onVessel(s);
        r.rec->flush();
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("SELECT sog, cog, depth FROM track_points"));
        QVERIFY(q.next());
        QCOMPARE(q.value(0).toDouble(), 2.0);
        QCOMPARE(q.value(1).toDouble(), 1.0);
        QCOMPARE(q.value(2).toDouble(), 12.5);
    }
    void setVisibleIsStored() {
        Rig r;
        const qint64 id = r.tracks->create(0);
        r.tracks->setVisible(id, false);
        QVERIFY(!r.tracks->list()[0].visible);
        r.tracks->setVisible(id, true);
        QVERIFY(r.tracks->list()[0].visible);
    }
    void removeDeletesThePointsToo() {
        Rig r;
        const qint64 a = r.tracks->create(0), b = r.tracks->create(10);
        TrackPoint p;
        p.lat = 1; p.lon = 1;
        QVERIFY(r.tracks->append(a, {p, p}));
        QVERIFY(r.tracks->append(b, {p}));
        r.tracks->remove(a);
        QCOMPARE(r.tracks->list().size(), 1);
        QCOMPARE(r.rows("track_points"), 1);
        QCOMPARE(r.tracks->points(a).size(), 0);
    }

    // A failed write must not let its points land in another track or in track_id 0.
    void failedWriteNeverMovesPointsToAnotherTrack() {
        Rig r(true, 1, 0);
        const QRegularExpression failed("cannot write track points"), dropped("dropping (\\d+) unwritten");
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("ALTER TABLE track_points RENAME TO track_points_off")); // writes now fail
        r.feed(0, 47.0);
        r.feed(1, 47.001);
        const qint64 first = r.rec->activeId();
        QTest::ignoreMessage(QtWarningMsg, failed);
        r.rec->flush();
        QTest::ignoreMessage(QtWarningMsg, failed); // the flush that starts the next track
        QTest::ignoreMessage(QtWarningMsg, dropped);
        r.feed(2000, 48.0);
        const qint64 second = r.rec->activeId();
        QVERIFY(second != first);
        QVERIFY(q.exec("ALTER TABLE track_points_off RENAME TO track_points"));
        r.rec->flush();
        QCOMPARE(r.stored(first), 0);
        QCOMPARE(r.stored(second), 1);
        // Recording off after a failed write: nothing is orphaned.
        QVERIFY(q.exec("ALTER TABLE track_points RENAME TO track_points_off"));
        r.feed(2001, 48.001);
        QTest::ignoreMessage(QtWarningMsg, failed);
        QTest::ignoreMessage(QtWarningMsg, dropped);
        r.settings->setTrackRecording(false);
        QVERIFY(q.exec("ALTER TABLE track_points_off RENAME TO track_points"));
        QCOMPARE(r.rows("track_points"), 1);
        QVERIFY(q.exec("SELECT count(*) FROM track_points WHERE track_id = 0") && q.next());
        QCOMPARE(q.value(0).toInt(), 0);
    }

    // A failing UPDATE of `ended` reports its own error, not the INSERT's.
    void failedEndedUpdateReportsItsOwnError() {
        Rig r;
        const qint64 id = r.tracks->create(0);
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("CREATE TRIGGER no_updates BEFORE UPDATE ON tracks BEGIN SELECT RAISE(ABORT, 'updates are off'); END"));
        TrackPoint p;
        p.t = 1; p.lat = 1; p.lon = 1;
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("cannot write track points: .*updates are off"));
        QVERIFY(!r.tracks->append(id, {p}));
        QCOMPARE(r.rows("track_points"), 0); // rolled back
    }
    // Writes that keep failing: the buffer never holds more than one batch, and each failed batch
    // is one write warning and one drop warning, not one per point.
    void failingWritesKeepTheBufferToOneBatch() {
        Rig r(true, 1, 0);
        QTest::failOnWarning(QRegularExpression(".*"));
        QSqlQuery q(r.store->db());
        QVERIFY(q.exec("ALTER TABLE track_points RENAME TO track_points_off")); // writes now fail
        for (int batch = 0; batch < 3; ++batch) {
            QTest::ignoreMessage(QtWarningMsg, QRegularExpression("cannot write track points"));
            QTest::ignoreMessage(QtWarningMsg, QRegularExpression("dropping 20 unwritten track points"));
        }
        for (int i = 0; i < 60; ++i) r.feed(i, 47.0 + i * 1e-4); // batches full at 19, 39 and 59
        r.feed(60, 47.0 + 60 * 1e-4);
        QVERIFY(q.exec("ALTER TABLE track_points_off RENAME TO track_points"));
        r.rec->flush();
        QCOMPARE(r.stored(r.rec->activeId()), 1); // the dropped batches are gone, the newer point is kept
    }

    void controllerShowsActiveAlwaysAndOthersWhenVisible() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        QSignalSpy finished(&c, &TracksController::finishedChanged);
        // Track one, two points; then a gap and track two.
        r.feed(0, 47.0); r.feed(1, 47.001);
        r.feed(1000, 48.0); r.feed(1001, 48.001);
        r.rec->flush();
        c.refresh();
        QCOMPARE(c.tracks().size(), 2);
        QCOMPARE(c.finished().size(), 1);
        QCOMPARE(c.active().size(), 2);
        const qint64 first = c.tracks().at(1).toMap()["id"].toLongLong();
        const auto before = finished.size();
        c.setVisible(first, false);
        QCOMPARE(c.finished().size(), 0);
        QCOMPARE(finished.size(), before + 1); // a visibility change rebuilds the finished tracks
        c.setVisible(first, true);
        QCOMPARE(c.finished().size(), 1);
        QCOMPARE(c.finished()[0].size(), 2);
        QCOMPARE(finished.size(), before + 2);
        // Hiding the active track does not hide it.
        c.setVisible(r.rec->activeId(), false);
        QCOMPARE(c.active().size(), 2);
        QCOMPARE(c.finished().size(), 1);
    }
    // The cost of a kept point must not grow with history: only the active track changes.
    void keptPointDoesNotRebuildFinishedTracks() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0); r.feed(1, 47.001);
        r.feed(1000, 48.0);
        QCOMPARE(c.finished().size(), 1);
        QSignalSpy finished(&c, &TracksController::finishedChanged);
        QSignalSpy active(&c, &TracksController::activeChanged);
        r.feed(1001, 48.001);
        r.feed(1002, 48.002);
        QCOMPARE(finished.size(), 0);
        QCOMPARE(active.size(), 2);
        QCOMPARE(c.active().size(), 3);
        r.rec->flush();
        c.refresh(); // the tracks page refreshes every 5 s
        c.refresh();
        QCOMPARE(finished.size(), 0);
        // Recording off: the active track joins the finished ones.
        r.settings->setTrackRecording(false);
        QCOMPARE(finished.size(), 1);
        QCOMPARE(c.finished().size(), 2);
        QCOMPARE(c.active().size(), 0);
    }
    // Finished tracks never change, so each is read from the database once: the tracks page's
    // refresh, a visibility change and the end of a track read the same number of tracks however
    // many finished tracks there are.
    void pointReadsDoNotGrowWithFinishedTracks() {
        QList<QList<int>> readsPerStep;
        for (int n : {3, 12}) {
            Rig r(true, 1, 0);
            for (int k = 0; k < n; ++k) {
                const qint64 id = r.tracks->create(k * 100);
                TrackPoint a, b;
                a.t = k * 100; a.lat = 47.0 + k * 0.01; a.lon = -122.0;
                b.t = k * 100 + 10; b.lat = a.lat + 0.001; b.lon = -122.0;
                QVERIFY(r.tracks->append(id, {a, b}));
            }
            TracksController c(*r.tracks, *r.rec);
            QCOMPARE(c.finished().size(), n);
            QList<int> reads;
            int before = r.tracks->pointReads();
            const auto step = [&] {
                reads.append(r.tracks->pointReads() - before);
                before = r.tracks->pointReads();
            };
            c.refresh();
            c.refresh();
            step();
            const qint64 oldest = c.tracks().constLast().toMap()["id"].toLongLong();
            c.setVisible(oldest, false);
            step();
            c.setVisible(oldest, true);
            step();
            QCOMPARE(c.finished().size(), n);
            QCOMPARE(c.finished().constLast().size(), 2);
            r.feed(10000, 48.0);
            r.feed(10001, 48.001);
            r.feed(20000, 49.0); // a gap: the recorded track is now a finished one
            step();
            QCOMPARE(c.finished().size(), n + 1);
            QCOMPARE(c.finished().constFirst().size(), 2);
            readsPerStep.append(reads);
        }
        QCOMPARE(readsPerStep[1], readsPerStep[0]);
        QCOMPARE(readsPerStep[0].mid(0, 3), (QList<int>{0, 0, 0})); // refresh and visibility read nothing
    }
    void controllerRowsCarryTheDisplayFields() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0); r.feed(60, 47.01);
        r.rec->flush();
        c.refresh();
        const QVariantMap row = c.tracks().at(0).toMap();
        QCOMPARE(row["points"].toInt(), 2);
        QCOMPARE(row["durationS"].toDouble(), 60.0);
        QVERIFY(row["distanceM"].toDouble() > 1000);
        QVERIFY(row["active"].toBool());
        QVERIFY(row["visible"].toBool());
        QVERIFY(!row["name"].toString().isEmpty());
    }
    void controllerRefusesToDeleteTheActiveTrack() {
        Rig r;
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0);
        r.rec->flush();
        c.remove(r.rec->activeId());
        QCOMPARE(r.tracks->list().size(), 1);
        r.settings->setTrackRecording(false);
        c.remove(r.tracks->list()[0].id);
        QCOMPARE(r.tracks->list().size(), 0);
        QCOMPARE(c.tracks().size(), 0);
    }
    void controllerFollowsANewActiveTrack() {
        Rig r(true, 1, 0);
        TracksController c(*r.tracks, *r.rec);
        r.feed(0, 47.0); r.feed(1, 47.001);
        r.feed(2000, 48.0); // a new track: the first one is now finished
        QCOMPARE(c.finished().size(), 1);
        QCOMPARE(c.active().size(), 1);
    }

    // Review Focus 4: SIGKILL a recording child after 25 synthetic seconds of points; the database
    // must be intact and what it holds a prefix of what was sent.
    void powerCutKeepsAPrefixOfTheTrack() {
        QTemporaryDir t;
        QProcess child;
        child.setProgram(QCoreApplication::applicationFilePath());
        child.setArguments({"--recorder", t.path()});
        child.setProcessChannelMode(QProcess::SeparateChannels);
        child.start();
        QVERIFY2(child.waitForStarted(10000), "child start");
        int sent = -1;
        QByteArray buf;
        QElapsedTimer clock;
        clock.start();
        while (sent < 25 && clock.elapsed() < 60000) {
            if (!child.waitForReadyRead(1000) && child.state() != QProcess::Running) break;
            buf += child.readAllStandardOutput();
            const auto lines = buf.split('\n');
            if (lines.size() >= 2) sent = lines[lines.size() - 2].toInt();
        }
        child.kill(); // SIGKILL
        QVERIFY(child.waitForFinished(10000));
        QVERIFY2(sent >= 25, qPrintable(QStringLiteral("child only sent %1 points").arg(sent)));
        QCOMPARE(child.exitStatus(), QProcess::CrashExit);

        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QSqlQuery q((*s)->db());
        QVERIFY(q.exec("PRAGMA integrity_check") && q.next());
        QCOMPARE(q.value(0).toString(), QStringLiteral("ok"));
        TrackStore ts(**s);
        const auto l = ts.list();
        QCOMPARE(l.size(), 1);
        const auto pts = ts.points(l[0].id);
        QVERIFY2(pts.size() >= 20, qPrintable(QStringLiteral("stored %1 points").arg(pts.size())));
        for (qsizetype i = 0; i < pts.size(); ++i) {
            QVERIFY2(std::abs(pts[i].lat - (47.0 + double(i) * 1e-4)) < 1e-9, "stored points are a prefix of the sent ones");
            QCOMPARE(pts[i].lon, -122.0);
        }
    }
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments();
    if (const int i = int(args.indexOf("--recorder")); i >= 0 && i + 1 < args.size())
        return runRecorder(args[i + 1]);
    TstTracks t;
    return QTest::qExec(&t, argc, argv);
}

#include "tst_tracks.moc"
