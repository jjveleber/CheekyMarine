#pragma once
#include <QDateTime>
#include <QSqlDatabase>
#include <QString>
#include <QVersionNumber>
#include <expected>
#include <functional>
#include <memory>

enum class StoreError { NewerMajor, Corrupt, Io };

// SQLite file <dir>/plotter.db: WAL + synchronous=FULL, so a power cut leaves the last committed
// state. Owns one uniquely named connection, removed on destruction.
class Store {
public:
    static inline const QVersionNumber kSchemaVersion{1, 0, 0};

    static std::expected<std::unique_ptr<Store>, StoreError> open(QString dir);
    // Renames plotter.db (and -wal, -shm) to plotter.db.bad-YYYYMMDD-HHMMSS[-N][-wal|-shm], N from 2
    // when a name is taken; returns the new main file path (empty if there was nothing to move), or
    // the error when any of the three could not be moved (a partial move says where the rest went).
    // Destroy any Store on dir first. `now` and `rename` (QFile::rename when empty) are test seams.
    static std::expected<QString, QString> moveAside(
        QString dir, const QDateTime& now = QDateTime::currentDateTime(),
        const std::function<bool(const QString& from, const QString& to)>& rename = {});

    ~Store();
    Store(const Store&) = delete;
    Store& operator=(const Store&) = delete;

    QSqlDatabase db() const { return QSqlDatabase::database(m_conn, false); }
    // The version recorded in the file. A newer minor/patch than kSchemaVersion is kept, never lowered.
    QVersionNumber schemaVersion() const { return m_version; }

private:
    explicit Store(QString conn) : m_conn(std::move(conn)) {}
    std::expected<void, StoreError> init();

    QString m_conn;
    QVersionNumber m_version;
};
