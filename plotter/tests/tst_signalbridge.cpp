#include "core/SignalBridge.h"
#include "core/Tracks.h"
#include <QEventLoop>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QTimer>
#include <QtTest>
#include <csignal>

namespace {

// Raises sig with a bridge installed and returns the signal number it reported, or 0 on timeout.
// The signal quits the loop the way main.cpp quits the app.
int bridged(int sig) {
    SignalBridge b{sig};
    QEventLoop loop;
    int got = 0;
    QObject::connect(&b, &SignalBridge::signaled, &loop, [&](int s) {
        got = s;
        loop.quit();
    });
    QTimer::singleShot(5000, &loop, &QEventLoop::quit);
    raise(sig);
    loop.exec();
    return got;
}

} // namespace

class TstSignalBridge : public QObject {
    Q_OBJECT
private slots:
    void sigtermFlushesBufferedPoints() {
        QTemporaryDir dir;
        auto s = Store::open(dir.path());
        QVERIFY(s);
        auto store = std::move(*s);
        Settings settings(*store);
        settings.setTrackRecording(true);
        settings.setTrackIntervalS(1);
        settings.setTrackMinDistanceM(0);
        TrackStore tracks(*store);
        double now = 1000;
        auto rec = std::make_unique<TrackRecorder>(tracks, settings, [&] { return now; });
        for (int i = 0; i < 3; ++i) {
            now = 1000 + i * 2;
            VesselState v;
            v.t = now;
            v.lat = 47.9 + i * 0.001;
            v.lon = -122.23;
            rec->onVessel(v);
        }
        { // the points are waiting in the buffer, not yet written
            QSqlQuery q(store->db());
            QVERIFY(q.exec("SELECT count(*) FROM track_points") && q.next());
            QCOMPARE(q.value(0).toInt(), 0);
        }
        QCOMPARE(bridged(SIGTERM), SIGTERM);
        rec.reset();
        QSqlQuery q(store->db());
        QVERIFY(q.exec("SELECT count(*) FROM track_points") && q.next());
        QCOMPARE(q.value(0).toInt(), 3);
    }
    void sigintIsReported() { QCOMPARE(bridged(SIGINT), SIGINT); }
    void sighupIsReported() { QCOMPARE(bridged(SIGHUP), SIGHUP); }
    // A signal the process was told to ignore (SIGHUP under nohup) stays ignored.
    void ignoredSignalStaysIgnored() {
        ::signal(SIGHUP, SIG_IGN);
        int got = 0;
        {
            SignalBridge b{SIGHUP};
            QObject::connect(&b, &SignalBridge::signaled, [&](int s) { got = s; });
            raise(SIGHUP); // would end the process if the default action were back
            QEventLoop loop;
            QTimer::singleShot(200, &loop, &QEventLoop::quit);
            loop.exec();
        }
        struct sigaction now {};
        QVERIFY(::sigaction(SIGHUP, nullptr, &now) == 0);
        const bool stillIgnored = now.sa_handler == SIG_IGN;
        ::signal(SIGHUP, SIG_DFL);
        QCOMPARE(got, 0);
        QVERIFY(stillIgnored);
    }
};

QTEST_MAIN(TstSignalBridge)
#include "tst_signalbridge.moc"
