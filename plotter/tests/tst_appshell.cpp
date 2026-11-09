#include "core/AppInfo.h"
#include "core/Recovery.h"
#include "core/N2kClient.h"
#include "core/Store.h"
#include "core/WindowOptions.h"
#include <QDir>
#include <QGuiApplication>
#include <QFile>
#include <QScreen>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QWindow>
#include <QtTest>

namespace {
PackInfo pack(const char* kind, const char* region, int major, int minor, const char* refused = "") {
    PackInfo p;
    p.kind = kind;
    p.region = region;
    p.version = QVersionNumber(major, minor, 0);
    p.dir = QStringLiteral("/packs/%1-%2-%3.%4.0").arg(kind, region).arg(major).arg(minor);
    p.notice = QStringLiteral("%1 notice").arg(kind);
    p.refused = refused;
    return p;
}

void writeFile(const QString& path, const QByteArray& bytes) {
    QFile f(path);
    QVERIFY(f.open(QIODevice::WriteOnly));
    f.write(bytes);
}

QString dbPath(const QTemporaryDir& d) { return QDir(d.path()).filePath("plotter.db"); }
} // namespace

class TstAppShell : public QObject {
    Q_OBJECT
private slots:
    void appInfoPacks() {
        const QList<PackInfo> scanned{pack("charts", "puget-north", 1, 0), pack("charts", "puget-north", 1, 2),
                                      pack("bathy", "puget-north", 1, 0), pack("bathy", "other", 2, 0),
                                      pack("charts", "puget-north", 9, 0, "schema 2 not supported")};
        const AppInfo info(scanned, {scanned[2], scanned[1]});
        QCOMPARE(info.appVersion(), QStringLiteral(PLOTTER_EXPECTED_VERSION));
        QCOMPARE(info.packsInUse().size(), 2);
        const QVariantMap charts = info.packsInUse().at(0).toMap();
        QCOMPARE(charts.value("kind").toString(), QStringLiteral("charts"));
        QCOMPARE(charts.value("version").toString(), QStringLiteral("1.2.0"));
        QCOMPARE(charts.value("region").toString(), QStringLiteral("puget-north"));
        QCOMPARE(charts.value("notice").toString(), QStringLiteral("charts notice"));
        QCOMPARE(info.packsInUse().at(1).toMap().value("version").toString(), QStringLiteral("1.0.0"));
        QCOMPARE(info.packs().size(), 5);
        const QVariantMap refused = info.packs().at(4).toMap();
        QCOMPARE(refused.value("refused").toString(), QStringLiteral("schema 2 not supported"));
        QCOMPARE(refused.value("inUse").toBool(), false);
        QCOMPARE(info.packs().at(1).toMap().value("inUse").toBool(), true);
        QCOMPARE(info.packs().at(0).toMap().value("inUse").toBool(), false);
        QCOMPARE(info.packs().at(2).toMap().value("inUse").toBool(), true);
        QCOMPARE(info.packs().at(3).toMap().value("inUse").toBool(), false);
    }

    void fullscreenIgnoresWindowSize() {
        QWindow w;
        w.show();
        applyWindowOptions(w, true, QSize(300, 200));
        QVERIFY(w.windowState() & Qt::WindowFullScreen);
        QVERIFY(w.isVisible());
        QVERIFY(w.size() != QSize(300, 200) || QGuiApplication::primaryScreen()->size() == QSize(300, 200));
    }

    void windowSizeAppliesWithoutFullscreen() {
        QWindow w;
        w.show();
        applyWindowOptions(w, false, QSize(300, 200));
        QCOMPARE(w.size(), QSize(300, 200));
        QVERIFY(!(w.windowState() & Qt::WindowFullScreen));
    }

    void platformProblemNamesOffscreen() {
        for (const QString& name : {QStringLiteral("offscreen"), QStringLiteral("minimal")})
            QCOMPARE(platformProblem(name),
                     QStringLiteral("renders need a GL display: QT_QPA_PLATFORM %1 cannot draw the chart").arg(name));
        QVERIFY(platformProblem("xcb").isEmpty());
        QVERIFY(platformProblem("wayland").isEmpty());
    }

    void appInfoNoPacks() {
        const AppInfo info({});
        QVERIFY(info.packsInUse().isEmpty());
    }

    void aboutListsEveryPack() {
        const char* regions[] = {"f", "a", "e", "b", "d", "c"};
        QList<PackInfo> inUse;
        for (const char* r : regions) inUse.append(pack("bathy", r, 1, 0));
        for (const char* r : regions) inUse.append(pack("charts", r, 1, 0));
        const AppInfo info(inUse, inUse);
        QCOMPARE(info.packsInUse().size(), 12);
        QStringList got;
        for (const QVariant& v : info.packsInUse()) got << v.toMap().value("kind").toString() + v.toMap().value("region").toString();
        QCOMPARE(got, (QStringList{"chartsa", "chartsb", "chartsc", "chartsd", "chartse", "chartsf",
                                   "bathya", "bathyb", "bathyc", "bathyd", "bathye", "bathyf"}));
    }

    void inUseFollowsController() {
        // A stale merge falls back to the one newest single pack per kind.
        const QList<PackInfo> scanned{pack("charts", "a", 1, 0), pack("charts", "b", 1, 1), pack("bathy", "a", 1, 0)};
        const AppInfo info(scanned, {scanned[1], scanned[2]}, {}, "Chart packs are not merged.");
        QCOMPARE(info.packNotice(), QStringLiteral("Chart packs are not merged."));
        QCOMPARE(info.packs().at(0).toMap().value("inUse").toBool(), false);
        QCOMPARE(info.packs().at(1).toMap().value("inUse").toBool(), true);
        QCOMPARE(info.packs().at(2).toMap().value("inUse").toBool(), true);
    }

    void appInfoSchemaMismatch() {
        AppInfo info({});
        QSignalSpy spy(&info, &AppInfo::schemaMismatchChanged);
        info.setDaemonVersion("0.3.0");
        QCOMPARE(info.daemonVersion(), QStringLiteral("0.3.0"));
        QVERIFY(!info.schemaMismatch());
        info.setSchemaMismatch(2);
        QVERIFY(info.schemaMismatch());
        QCOMPARE(spy.count(), 1);
        // The client sends the hello's version first, then the mismatch again if it still applies.
        info.setDaemonVersion("0.4.0");
        QVERIFY(!info.schemaMismatch());
        QCOMPARE(spy.count(), 2);
    }

    void recoveryStartFreshMovesAsideAndOpens() {
        QTemporaryDir d;
        writeFile(dbPath(d), QByteArray(4096, 'x'));
        auto r = Store::open(d.path());
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), StoreError::Corrupt);
        writeFile(dbPath(d) + "-wal", "junk"); // a left-over WAL goes aside with the file

        Recovery rec(d.path(), r.error());
        QVERIFY(!rec.reason().isEmpty());
        QVERIFY(!rec.canRetry());
        QSignalSpy done(&rec, &Recovery::recovered);
        rec.startFresh();
        QCOMPARE(done.count(), 1);
        QVERIFY(rec.error().isEmpty());
        QVERIFY(rec.movedTo().startsWith(dbPath(d) + ".bad-"));
        QVERIFY(QFile::exists(rec.movedTo()));
        QVERIFY(QFile::exists(rec.movedTo() + "-wal"));
        auto store = rec.takeStore();
        QVERIFY(store);
        QCOMPARE(store->schemaVersion(), Store::kSchemaVersion);
    }

    void recoveryFailedMoveDoesNotReopen() {
        QTemporaryDir d;
        writeFile(dbPath(d), QByteArray(4096, 'x'));
        QFile::setPermissions(d.path(), QFile::ReadOwner | QFile::ExeOwner); // rename impossible
        if (QFileInfo(d.path()).isWritable()) QSKIP("running with permissions that ignore the mode bits");
        Recovery rec(d.path(), StoreError::Corrupt);
        QSignalSpy done(&rec, &Recovery::recovered);
        QSignalSpy err(&rec, &Recovery::errorChanged);
        rec.startFresh();
        QFile::setPermissions(d.path(), QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
        QCOMPARE(done.count(), 0);
        QCOMPARE(err.count(), 1);
        QVERIFY(rec.error().contains("could not be moved aside"));
        QVERIFY(!rec.takeStore());
        QCOMPARE(QFile(dbPath(d)).size(), 4096); // the bad file is untouched
    }

    void recoveryIoRetry() {
        QTemporaryDir d;
        Recovery rec(d.path(), StoreError::Io);
        QVERIFY(rec.canRetry());
        QVERIFY(rec.reason().contains("could not be opened"));
        QSignalSpy done(&rec, &Recovery::recovered);
        rec.retry(); // the directory is fine now
        QCOMPARE(done.count(), 1);
        QVERIFY(rec.takeStore());
        QVERIFY(rec.movedTo().isEmpty());
    }

    void recoveryRetryStillFailing() {
        QTemporaryDir d;
        writeFile(dbPath(d), QByteArray(4096, 'x'));
        Recovery rec(d.path(), StoreError::Io);
        QSignalSpy done(&rec, &Recovery::recovered);
        rec.retry();
        QCOMPARE(done.count(), 0);
        QVERIFY(rec.error().contains("still"));
        QCOMPARE(QFile(dbPath(d)).size(), 4096);
    }

    void connectAppInfoForwardsDaemonSignals() {
        N2kClient c(QStringLiteral("/nonexistent"));
        AppInfo i({});
        connectAppInfo(c, i);
        emit c.daemonVersion(QStringLiteral("1.2.3"));
        QCOMPARE(i.daemonVersion(), QStringLiteral("1.2.3"));
        emit c.schemaMismatch(2);
        QVERIFY(i.schemaMismatch());
        emit c.daemonVersion(QStringLiteral("1.2.3"));
        QVERIFY(!i.schemaMismatch());
    }

    void frameStatsSummary() {
        QCOMPARE(frameStatsLine({16, 17, 16, 120, 16}), QStringLiteral("frame-stats: frames 5 max 120 ms p99 120 ms over50 1"));
        QCOMPARE(frameStatsLine({}), QStringLiteral("frame-stats: frames 0 max 0 ms p99 0 ms over50 0"));
    }

    void writeStatsSummary() {
        QCOMPARE(writeStatsLine({500, 1250, 51000, 800}),
                 QStringLiteral("track-writes: writes 4 max 51.00 ms p99 51.00 ms over50 1"));
        QCOMPARE(writeStatsLine({50000, 1000}), QStringLiteral("track-writes: writes 2 max 50.00 ms p99 50.00 ms over50 0"));
        QCOMPARE(writeStatsLine({}), QStringLiteral("track-writes: writes 0 max 0.00 ms p99 0.00 ms over50 0"));
    }

    void readSetVersionReadsSet() {
        QTemporaryDir t;
        const QString lock = t.filePath("cheekymarine.lock");
        QFile f(lock);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write("# CheekyMarine set lock. Format: see installer/README.md.\n"
                "schema=1\nset=0.1.0\nn2kd.version=0.1.0\nn2kd.tag=v0.1.0\n"
                "n2kd.asset=n2kd-0.1.0-x86_64.tar.gz\nn2kd.sha256=00\n"
                "charts.version=1.1.0\ncharts.tag=charts-puget-north-v1.1.0\n"
                "charts.asset=charts-puget-north-1.1.0.tar\ncharts.sha256=00\ncharts.schema=1\n"
                "bathy.version=1.1.0\nbathy.tag=bathy-puget-north-v1.1.0\n"
                "bathy.asset=bathy-puget-north-1.1.0.tar\nbathy.sha256=00\nbathy.schema=1\n"
                "plotter.version=0.1.0\nplotter.tag=plotter-v0.1.0\n"
                "plotter.asset=cheekyplotter-0.1.0-x86_64.tar.gz\nplotter.sha256=00\n"
                "plotter.pack_schema_min=1\nplotter.pack_schema_max=1\n");
        f.close();
        QCOMPARE(readSetVersion(lock), QString("0.1.0"));
    }
    void readSetVersionEmptyWhenMissing() {
        QTemporaryDir t;
        QVERIFY(readSetVersion(t.filePath("nope.lock")).isEmpty());
    }
    void setVersionReadsSchema2Lock() {
        QTemporaryDir t;
        const QString lock = t.filePath("cheekymarine.lock");
        writeFile(lock, "schema=2\nset=0.3.0\n");
        QCOMPARE(readSetVersion(lock), QString("0.3.0"));
    }
    void setVersionStillReadsSchema1Lock() {
        QTemporaryDir t;
        const QString lock = t.filePath("cheekymarine.lock");
        writeFile(lock, "schema=1\nset=0.2.0\n");
        QCOMPARE(readSetVersion(lock), QString("0.2.0"));
    }
    void readSetVersionEmptyOnOtherSchema() {
        QTemporaryDir t;
        const QString lock = t.filePath("cheekymarine.lock");
        QFile f(lock);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.write("# comment\nschema=3\nset=0.1.0\n");
        f.close();
        QVERIFY(readSetVersion(lock).isEmpty());
    }

    void reasons() {
        QVERIFY(storeErrorReason(StoreError::NewerMajor).contains("newer version"));
        QVERIFY(storeErrorReason(StoreError::Corrupt).contains("damaged"));
        QVERIFY(storeErrorReason(StoreError::Io).contains("could not be opened"));
    }
};

QTEST_MAIN(TstAppShell)
#include "tst_appshell.moc"
