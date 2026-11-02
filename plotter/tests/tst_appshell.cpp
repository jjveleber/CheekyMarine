#include "core/AppInfo.h"
#include "core/Recovery.h"
#include "core/Store.h"
#include <QDir>
#include <QFile>
#include <QSignalSpy>
#include <QTemporaryDir>
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
        const AppInfo info({pack("charts", "puget-north", 1, 0), pack("charts", "puget-north", 1, 2),
                            pack("bathy", "puget-north", 1, 0), pack("bathy", "other", 2, 0),
                            pack("charts", "puget-north", 9, 0, "schema 2 not supported")});
        QCOMPARE(info.appVersion(), QStringLiteral(PLOTTER_EXPECTED_VERSION));
        QCOMPARE(info.chartsPack().value("version").toString(), QStringLiteral("1.2.0"));
        QCOMPARE(info.chartsPack().value("region").toString(), QStringLiteral("puget-north"));
        QCOMPARE(info.chartsPack().value("notice").toString(), QStringLiteral("charts notice"));
        QCOMPARE(info.bathyPack().value("version").toString(), QStringLiteral("1.0.0"));
        QCOMPARE(info.packs().size(), 5);
        const QVariantMap refused = info.packs().at(4).toMap();
        QCOMPARE(refused.value("refused").toString(), QStringLiteral("schema 2 not supported"));
        QCOMPARE(refused.value("inUse").toBool(), false);
        QCOMPARE(info.packs().at(1).toMap().value("inUse").toBool(), true);
        QCOMPARE(info.packs().at(0).toMap().value("inUse").toBool(), false);
        QCOMPARE(info.packs().at(2).toMap().value("inUse").toBool(), true);
        QCOMPARE(info.packs().at(3).toMap().value("inUse").toBool(), false);
    }

    void appInfoNoPacks() {
        const AppInfo info({});
        QVERIFY(info.chartsPack().isEmpty());
        QVERIFY(info.bathyPack().isEmpty());
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

    void reasons() {
        QVERIFY(storeErrorReason(StoreError::NewerMajor).contains("newer version"));
        QVERIFY(storeErrorReason(StoreError::Corrupt).contains("damaged"));
        QVERIFY(storeErrorReason(StoreError::Io).contains("could not be opened"));
    }
};

QTEST_GUILESS_MAIN(TstAppShell)
#include "tst_appshell.moc"
