#pragma once
#include <QSqlDatabase>
#include <QString>
#include <QVersionNumber>
#include <expected>
#include <memory>

enum class StoreError { NewerMajor, Corrupt, Io };

// SQLite file <dir>/plotter.db: WAL + synchronous=FULL, so a power cut leaves the last committed
// state. Owns one uniquely named connection, removed on destruction.
class Store {
public:
    static inline const QVersionNumber kSchemaVersion{1, 0, 0};

    static std::expected<std::unique_ptr<Store>, StoreError> open(QString dir);
    // Renames plotter.db (and -wal, -shm) to plotter.db.bad-YYYYMMDD-HHMMSS[-wal|-shm]; returns the
    // new main file path (empty if there was nothing to move). Destroy any Store on dir first.
    static QString moveAside(QString dir);

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
