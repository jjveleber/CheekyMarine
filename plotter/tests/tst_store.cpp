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

// Child of the multi-statement power-cut test: commits groups of three rows (g<n>-a, -b, -c) in one
// transaction each, like a settings save, reporting each committed group on stdout.
int runGroupWriter(const QString& dir) {
    auto store = Store::open(dir);
    if (!store)
        return 2;
    QSqlDatabase db = (*store)->db();
    QSqlQuery q(db);
    for (int g = 0;; ++g) {
        if (!db.transaction())
            return 3;
        for (const char* part : {"a", "b", "c"}) {
            q.prepare(QStringLiteral("INSERT INTO settings(key, value) VALUES(?, ?)"));
            q.addBindValue(QStringLiteral("g%1-%2").arg(g).arg(QLatin1String(part)));
            q.addBindValue(QString::number(g));
            if (!q.exec())
                return 3;
        }
        if (!db.commit())
            return 3;
        std::printf("%d\n", g);
        std::fflush(stdout);
    }
}

// Starts this test binary as a child in `mode` on `dir`, reads the numbers it reports until one
// reaches `target` (or 60 s pass), then SIGKILLs it. Returns the last number reported, -1 for none.
int killChildAfter(QProcess& child, const QString& mode, const QString& dir, int target) {
    child.setProgram(QCoreApplication::applicationFilePath());
    child.setArguments({mode, dir});
    child.setProcessChannelMode(QProcess::SeparateChannels);
    child.start();
    if (!child.waitForStarted(10000))
        return -1;
    int acked = -1;
    QByteArray buf;
    QElapsedTimer clock;
    clock.start();
    while (acked < target && clock.elapsed() < 60000) {
        if (!child.waitForReadyRead(1000) && child.state() != QProcess::Running)
            break;
        buf += child.readAllStandardOutput();
        const auto lines = buf.split('\n');
        if (lines.size() >= 2)
            acked = lines[lines.size() - 2].toInt();
    }
    child.kill(); // SIGKILL
    child.waitForFinished(10000);
    return acked;
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
    // A file with our tables but no schema_version is damaged, not an Io problem.
    void tablesWithoutSchemaVersionAreCorrupt() {
        QTemporaryDir t;
        rawExec(t.path(), {"CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)"});
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::Corrupt);
    }
    void emptySchemaVersionIsCorrupt() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        rawExec(t.path(), {"DELETE FROM schema_version"});
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::Corrupt);
    }
    // Several schema_version rows: the highest counts, whatever the row order.
    void severalSchemaVersionRowsUseTheHighest() {
        const QRegularExpression warning("2 schema_version rows");
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        rawExec(t.path(), {"INSERT INTO schema_version VALUES(1, 3, 0)"});
        {
            QTest::ignoreMessage(QtWarningMsg, warning);
            auto s = Store::open(t.path());
            QVERIFY(s.has_value());
            QCOMPARE((*s)->schemaVersion(), QVersionNumber(1, 3, 0));
        }
        rawExec(t.path(), {"DELETE FROM schema_version WHERE minor = 3", "INSERT INTO schema_version VALUES(2, 0, 0)"});
        QTest::ignoreMessage(QtWarningMsg, warning);
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::NewerMajor);
    }
    // SQLITE_CORRUPT raised by a migration statement is classified from that statement's error.
    // The file is valid up to its free list, which points past the end: the first page the
    // migration allocates is where SQLite finds the damage.
    void corruptionFoundByTheMigrationIsCorrupt() {
        QTemporaryDir t;
        rawExec(t.path(), {"PRAGMA user_version = 7"}); // one page, no tables
        QFile f(t.filePath("plotter.db"));
        QVERIFY(f.open(QIODevice::ReadWrite));
        QVERIFY(f.seek(32));
        const char freeList[8] = {0, 0, 0, 5, 0, 0, 0, 1}; // first free-list trunk page 5, 1 free page
        QCOMPARE(f.write(freeList, 8), qint64(8));
        f.close();
        auto s = Store::open(t.path());
        QVERIFY(!s.has_value());
        QCOMPARE(s.error(), StoreError::Corrupt);
    }
    void moveAsideThenOpen() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        const auto moved = Store::moveAside(t.path());
        QVERIFY(moved.has_value());
        QVERIFY(moved->contains(QRegularExpression(R"(plotter\.db\.bad-\d{8}-\d{6}$)")));
        QVERIFY(QFile::exists(*moved));
        QVERIFY(!QFile::exists(t.filePath("plotter.db")));
        QVERIFY(!QFile::exists(t.filePath("plotter.db-wal")));
        QVERIFY(!QFile::exists(t.filePath("plotter.db-shm")));
        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE((*s)->schemaVersion(), QVersionNumber(1, 0, 0));
    }
    void moveAsideNothingToMoveIsEmpty() {
        QTemporaryDir t;
        const auto moved = Store::moveAside(t.path());
        QVERIFY(moved.has_value());
        QVERIFY(moved->isEmpty());
    }
    // A name already taken (main, -wal or -shm) gets a numbered suffix; nothing is overwritten.
    void moveAsideTwiceInTheSameSecondKeepsBoth() {
        QTemporaryDir t;
        const QDateTime now(QDate(2026, 10, 31), QTime(12, 0, 0));
        { QVERIFY(Store::open(t.path()).has_value()); }
        const auto first = Store::moveAside(t.path(), now);
        QVERIFY(first.has_value());
        QVERIFY(first->endsWith("plotter.db.bad-20261031-120000"));
        { QVERIFY(Store::open(t.path()).has_value()); }
        const auto second = Store::moveAside(t.path(), now);
        QVERIFY2(second.has_value(), qPrintable(second.error_or(QString())));
        QVERIFY(second->endsWith("plotter.db.bad-20261031-120000-2"));
        QVERIFY(QFile::exists(*first));
        QVERIFY(QFile::exists(*second));
        QVERIFY(!QFile::exists(t.filePath("plotter.db")));
        { QVERIFY(Store::open(t.path()).has_value()); }
        QFile taken(t.filePath("plotter.db.bad-20261031-120000-3-wal"));
        QVERIFY(taken.open(QIODevice::WriteOnly));
        taken.close();
        const auto third = Store::moveAside(t.path(), now);
        QVERIFY(third.has_value());
        QVERIFY(third->endsWith("plotter.db.bad-20261031-120000-4"));
    }
    void moveAsideFailedRenameIsAnError() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        QFile::setPermissions(t.path(), QFile::ReadOwner | QFile::ExeOwner); // rename impossible
        const bool ignored = QFileInfo(t.path()).isWritable();
        const auto moved = Store::moveAside(t.path());
        QFile::setPermissions(t.path(), QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
        if (ignored)
            QSKIP("running with privileges that ignore directory permissions");
        QVERIFY(!moved.has_value());
        QVERIFY(moved.error().contains("plotter.db could not be moved aside"));
        QVERIFY(QFile::exists(t.filePath("plotter.db")));
    }
    // The main file moved but its -wal did not: reported, with where the main file went.
    void moveAsidePartialMoveIsAnError() {
        QTemporaryDir t;
        { QVERIFY(Store::open(t.path()).has_value()); }
        QFile wal(t.filePath("plotter.db-wal"));
        QVERIFY(wal.open(QIODevice::WriteOnly));
        wal.close();
        const auto failWal = [](const QString& from, const QString& to) {
            return !from.endsWith("-wal") && QFile::rename(from, to);
        };
        const QDateTime now(QDate(2026, 10, 31), QTime(12, 0, 0));
        const auto moved = Store::moveAside(t.path(), now, failWal);
        QVERIFY(!moved.has_value());
        QVERIFY(moved.error().contains("plotter.db-wal could not be moved aside"));
        QVERIFY(moved.error().contains("plotter.db.bad-20261031-120000"));
        QVERIFY(!QFile::exists(t.filePath("plotter.db")));
        QVERIFY(QFile::exists(t.filePath("plotter.db-wal")));
    }
    // Review Focus 4: SIGKILL a child mid-write; the database must open and pass integrity_check.
    void powerCutKeepsDatabaseIntact() {
        QTemporaryDir t;
        QProcess child;
        const int acked = killChildAfter(child, "--writer", t.path(), 200);
        QVERIFY2(acked >= 200, qPrintable(QStringLiteral("child only acknowledged %1 rows").arg(acked)));
        QCOMPARE(child.state(), QProcess::NotRunning);
        QCOMPARE(child.exitStatus(), QProcess::CrashExit);

        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE(scalar((*s)->db(), "PRAGMA integrity_check"), QStringLiteral("ok"));
        // Every row the child reported as committed must have survived.
        const int rows = scalar((*s)->db(), "SELECT count(*) FROM settings").toInt();
        QVERIFY2(rows >= acked + 1, qPrintable(QStringLiteral("rows %1 acked %2").arg(rows).arg(acked)));
    }
    // Review Focus 4 for multi-statement saves: a kill between the statements of a transaction
    // leaves each group all there or not there at all, and every reported group there.
    void powerCutKeepsMultiStatementSavesAllOrNothing() {
        QTemporaryDir t;
        QProcess child;
        const int acked = killChildAfter(child, "--group-writer", t.path(), 200);
        QVERIFY2(acked >= 200, qPrintable(QStringLiteral("child only acknowledged %1 groups").arg(acked)));
        QCOMPARE(child.state(), QProcess::NotRunning);
        QCOMPARE(child.exitStatus(), QProcess::CrashExit);

        auto s = Store::open(t.path());
        QVERIFY(s.has_value());
        QCOMPARE(scalar((*s)->db(), "PRAGMA integrity_check"), QStringLiteral("ok"));
        const QString groups = QStringLiteral(
            "SELECT substr(key, 1, instr(key, '-') - 1) AS g, count(*) AS n FROM settings GROUP BY g");
        QCOMPARE(scalar((*s)->db(), "SELECT count(*) FROM (" + groups + ") WHERE n != 3"), QStringLiteral("0"));
        const int complete = scalar((*s)->db(), "SELECT count(*) FROM (" + groups + ") WHERE n = 3").toInt();
        QVERIFY2(complete >= acked + 1, qPrintable(QStringLiteral("groups %1 acked %2").arg(complete).arg(acked)));
    }
};

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments();
    if (const int i = int(args.indexOf("--writer")); i >= 0 && i + 1 < args.size())
        return runWriter(args[i + 1]);
    if (const int i = int(args.indexOf("--group-writer")); i >= 0 && i + 1 < args.size())
        return runGroupWriter(args[i + 1]);
    TstStore t;
    return QTest::qExec(&t, argc, argv);
}

#include "tst_store.moc"
