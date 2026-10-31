#include "Store.h"
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSqlError>
#include <QSqlQuery>
#include <QUuid>
#include <array>
#include <functional>

namespace {

// apply returns the failing statement's error, or a QSqlError of type NoError.
struct Migration {
    QVersionNumber to;
    std::function<QSqlError(QSqlDatabase&)> apply;
};

QSqlError execAll(QSqlDatabase& db, std::initializer_list<const char*> sqls) {
    QSqlQuery q(db);
    for (const char* s : sqls)
        if (!q.exec(QString::fromLatin1(s)))
            return q.lastError();
    return {};
}

const std::array<Migration, 1> kMigrations{{
    {QVersionNumber(1, 0, 0),
     [](QSqlDatabase& db) {
         return execAll(db, {
             "CREATE TABLE schema_version(major INTEGER NOT NULL, minor INTEGER NOT NULL, patch INTEGER NOT NULL)",
             "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
             "CREATE TABLE tracks(id INTEGER PRIMARY KEY, name TEXT, started REAL, ended REAL, visible INTEGER)",
             "CREATE TABLE track_points(track_id INTEGER, t REAL, lat REAL, lon REAL, sog REAL, cog REAL, depth REAL)",
             "CREATE INDEX track_points_by_track ON track_points(track_id, t)"});
     }},
}};

StoreError classify(const QSqlError& e) {
    const int code = e.nativeErrorCode().toInt() & 0xff;
    return (code == 11 /*SQLITE_CORRUPT*/ || code == 26 /*SQLITE_NOTADB*/) ? StoreError::Corrupt : StoreError::Io;
}

} // namespace

std::expected<std::unique_ptr<Store>, StoreError> Store::open(QString dir) {
    if (!QDir(dir).exists() && !QDir().mkpath(dir))
        return std::unexpected(StoreError::Io);
    const QFileInfo fi(dir);
    if (!fi.isDir() || !fi.isReadable() || !fi.isWritable() || !fi.isExecutable())
        return std::unexpected(StoreError::Io);

    const QString conn = QStringLiteral("plotter-store-") + QUuid::createUuid().toString(QUuid::WithoutBraces);
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), conn);
        db.setDatabaseName(QDir(dir).filePath(QStringLiteral("plotter.db")));
        db.setConnectOptions(QStringLiteral("QSQLITE_BUSY_TIMEOUT=5000"));
    }
    std::unique_ptr<Store> s(new Store(conn)); // its destructor removes the connection on any failure below
    if (auto r = s->init(); !r)
        return std::unexpected(r.error());
    return s;
}

std::expected<void, StoreError> Store::init() {
    QSqlDatabase d = db();
    if (!d.open())
        return std::unexpected(classify(d.lastError()));
    QSqlQuery q(d);
    // The first statement that reads the file is where random bytes show up as SQLITE_NOTADB.
    if (!q.exec(QStringLiteral("PRAGMA journal_mode=WAL")) || !q.next())
        return std::unexpected(classify(q.lastError()));
    if (q.value(0).toString().toLower() != QLatin1String("wal"))
        return std::unexpected(StoreError::Io);
    if (!q.exec(QStringLiteral("PRAGMA synchronous=FULL")))
        return std::unexpected(classify(q.lastError()));

    QVersionNumber cur(0, 0, 0);
    if (!q.exec(QStringLiteral("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'")))
        return std::unexpected(classify(q.lastError()));
    if (q.next()) {
        if (!q.exec(QStringLiteral("SELECT count(*) FROM schema_version")) || !q.next())
            return std::unexpected(classify(q.lastError()));
        const int rows = q.value(0).toInt();
        if (rows == 0)
            return std::unexpected(StoreError::Corrupt);
        if (rows > 1)
            qWarning() << "plotter.db has" << rows << "schema_version rows; using the highest";
        if (!q.exec(QStringLiteral("SELECT major, minor, patch FROM schema_version ORDER BY major DESC, minor DESC, patch DESC LIMIT 1")) ||
            !q.next())
            return std::unexpected(classify(q.lastError()));
        cur = QVersionNumber(q.value(0).toInt(), q.value(1).toInt(), q.value(2).toInt());
    } else {
        // Tables without a version are not a file this app made; a fresh file has none.
        if (!q.exec(QStringLiteral("SELECT 1 FROM sqlite_master WHERE type='table'")))
            return std::unexpected(classify(q.lastError()));
        if (q.next())
            return std::unexpected(StoreError::Corrupt);
    }
    if (cur.majorVersion() > kSchemaVersion.majorVersion())
        return std::unexpected(StoreError::NewerMajor);

    for (const Migration& m : kMigrations) {
        if (QVersionNumber::compare(m.to, cur) <= 0)
            continue;
        if (!d.transaction())
            return std::unexpected(classify(d.lastError()));
        // Statement errors live on their QSqlQuery, not in d.lastError(): keep the failing one's.
        QSqlError err = m.apply(d);
        if (!err.isValid()) {
            QSqlQuery w(d);
            const bool ok = w.exec(QStringLiteral("DELETE FROM schema_version")) &&
                            w.prepare(QStringLiteral("INSERT INTO schema_version(major, minor, patch) VALUES(?,?,?)"));
            if (ok) {
                w.addBindValue(m.to.majorVersion());
                w.addBindValue(m.to.minorVersion());
                w.addBindValue(m.to.microVersion());
            }
            if (!ok || !w.exec())
                err = w.lastError();
        }
        if (!err.isValid() && !d.commit())
            err = d.lastError();
        if (err.isValid()) {
            d.rollback();
            return std::unexpected(classify(err));
        }
        cur = m.to;
    }
    m_version = cur;
    return {};
}

Store::~Store() {
    {
        QSqlDatabase d = QSqlDatabase::database(m_conn, false);
        if (d.isOpen())
            d.close();
    } // no QSqlDatabase copy may be alive when the connection is removed
    QSqlDatabase::removeDatabase(m_conn);
}

QString Store::moveAside(QString dir) {
    const QString base = QDir(dir).filePath(QStringLiteral("plotter.db"));
    const QString moved = base + QStringLiteral(".bad-") + QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss"));
    QString result;
    for (const QString& suffix : {QString(), QStringLiteral("-wal"), QStringLiteral("-shm")}) {
        if (QFile::exists(base + suffix) && QFile::rename(base + suffix, moved + suffix) && suffix.isEmpty())
            result = moved;
    }
    return result;
}
