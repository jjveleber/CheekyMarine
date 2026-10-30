#include "core/Store.h"
#include <QCoreApplication>
#include <QFile>
#include <QProcess>
#include <QRandomGenerator>
#include <QSqlError>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>
#include <cstdio>

namespace {

QString scalar(const QSqlDatabase& db, const QString& sql) {
    QSqlQuery q(db);
    if (!q.exec(sql) || !q.next())
        return QStringLiteral("<error: %1>").arg(q.lastError().text());
    return q.value(0).toString();
}

// Runs statements on a throwaway connection to plotter.db (used to fake files from other app versions).
void rawExec(const QString& dir, const QStringList& sqls) {
    const QString name = QStringLiteral("raw-") + QString::number(QRandomGenerator::global()->generate());
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), name);
        db.setDatabaseName(dir + QStringLiteral("/plotter.db"));
        QVERIFY2(db.open(), "raw open");
        QSqlQuery q(db);
        for (const QString& s : sqls)
            QVERIFY2(q.exec(s), qPrintable(s + ": " + q.lastError().text()));
    }
    QSqlDatabase::removeDatabase(name);
}

// Child of the power-cut test: inserts settings rows forever, reporting each committed one on stdout.
int runWriter(const QString& dir) {
    auto store = Store::open(dir);
    if (!store)
        return 2;
    QSqlDatabase db = (*store)->db();
    QSqlQuery q(db);
    q.prepare(QStringLiteral("INSERT INTO settings(key, value) VALUES(?, ?)"));
    for (int i = 0;; ++i) {
        q.addBindValue(QStringLiteral("k%1").arg(i));
        q.addBindValue(QString::number(i));
        if (!q.exec())
            return 3;
        std::printf("%d\n", i);
        std::fflush(stdout);
    }
}

} // namespace

class TstStore : public QObject {
    Q_OBJECT
private slots:
    void createsSchemaWalFull() {
        QTemporaryDir t;
        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE((*s)->schemaVersion(), QVersionNumber(1, 0, 0));
        QCOMPARE(scalar((*s)->db(), "PRAGMA journal_mode"), QStringLiteral("wal"));
        QCOMPARE(scalar((*s)->db(), "PRAGMA synchronous"), QStringLiteral("2"));
        for (const char* tbl : {"schema_version", "settings", "tracks", "track_points"})
            QCOMPARE(scalar((*s)->db(), QStringLiteral("SELECT count(*) FROM sqlite_master WHERE name='%1'").arg(tbl)),
                     QStringLiteral("1"));
        QCOMPARE(scalar((*s)->db(), "SELECT major||'.'||minor||'.'||patch FROM schema_version"), QStringLiteral("1.0.0"));
    }
    void reopenKeepsData() {
        QTemporaryDir t;
        {
            auto s = Store::open(t.path());
            QVERIFY(s.has_value());
            QSqlQuery q((*s)->db());
            QVERIFY(q.exec("INSERT INTO settings VALUES('a','1')"));
        }
        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE(scalar((*s)->db(), "SELECT value FROM settings WHERE key='a'"), QStringLiteral("1"));
    }
    void newerMajorRefused() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        rawExec(t.path(), {"UPDATE schema_version SET major=2, minor=0, patch=0"});
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::NewerMajor);
    }
    void newerMinorOpensAndIsNotLowered() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        rawExec(t.path(), {"UPDATE schema_version SET minor=3"});
        {
            auto s = Store::open(t.path());
            QVERIFY(s.has_value());
            QCOMPARE((*s)->schemaVersion(), QVersionNumber(1, 3, 0));
        }
        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE(scalar((*s)->db(), "SELECT major||'.'||minor||'.'||patch FROM schema_version"), QStringLiteral("1.3.0"));
    }
    void randomBytesIsCorrupt() {
        QTemporaryDir t;
        QFile f(t.filePath("plotter.db"));
        QVERIFY(f.open(QIODevice::WriteOnly));
        QByteArray junk(8192, 0);
        for (char& c : junk)
            c = char(QRandomGenerator::global()->bounded(256));
        f.write(junk);
        f.close();
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::Corrupt);
    }
    void unusablePathIsIo() {
        QTemporaryDir t;
        QFile f(t.filePath("afile"));
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.close();
        auto s = Store::open(t.filePath("afile")); // a file where a directory is needed
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::Io);

        QDir(t.path()).mkdir("locked");
        QFile::setPermissions(t.filePath("locked"), QFileDevice::Permissions());
        auto s2 = Store::open(t.filePath("locked"));
        QFile::setPermissions(t.filePath("locked"), QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);
        if (s2.has_value())
            QSKIP("running with privileges that ignore directory permissions");
        QCOMPARE(s2.error(), StoreError::Io);
    }
    void moveAsideThenOpen() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        const QString moved = Store::moveAside(t.path());
        QVERIFY(moved.contains(QRegularExpression(R"(plotter\.db\.bad-\d{8}-\d{6}$)")));
        QVERIFY(QFile::exists(moved));
        QVERIFY(!QFile::exists(t.filePath("plotter.db")));
        QVERIFY(!QFile::exists(t.filePath("plotter.db-wal")));
        QVERIFY(!QFile::exists(t.filePath("plotter.db-shm")));
        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE((*s)->schemaVersion(), QVersionNumber(1, 0, 0));
    }
    // Review Focus 4: SIGKILL a child mid-write; the database must open and pass integrity_check.
    void powerCutKeepsDatabaseIntact() {
        QTemporaryDir t;
        QProcess child;
        child.setProgram(QCoreApplication::applicationFilePath());
        child.setArguments({"--writer", t.path()});
        child.setProcessChannelMode(QProcess::SeparateChannels);
        child.start();
        QVERIFY2(child.waitForStarted(10000), "child start");
        int acked = -1;
        QByteArray buf;
        QElapsedTimer clock;
        clock.start();
        while (acked < 200 && clock.elapsed() < 60000) {
            if (!child.waitForReadyRead(1000) && child.state() != QProcess::Running)
                break;
            buf += child.readAllStandardOutput();
            const auto lines = buf.split('\n');
            if (lines.size() >= 2)
                acked = lines[lines.size() - 2].toInt();
        }
        child.kill(); // SIGKILL
        QVERIFY(child.waitForFinished(10000));
        QVERIFY2(acked >= 200, qPrintable(QStringLiteral("child only acknowledged %1 rows").arg(acked)));
        QCOMPARE(child.exitStatus(), QProcess::CrashExit);

        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE(scalar((*s)->db(), "PRAGMA integrity_check"), QStringLiteral("ok"));
        // Every row the child reported as committed must have survived.
        const int rows = scalar((*s)->db(), "SELECT count(*) FROM settings").toInt();
        QVERIFY2(rows >= acked + 1, qPrintable(QStringLiteral("rows %1 acked %2").arg(rows).arg(acked)));
    }
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments();
    if (const int i = int(args.indexOf("--writer")); i >= 0 && i + 1 < args.size())
        return runWriter(args[i + 1]);
    TstStore t;
    return QTest::qExec(&t, argc, argv);
}

#include "tst_store.moc"
