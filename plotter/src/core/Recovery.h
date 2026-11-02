#pragma once
#include "Store.h"
#include <QObject>
#include <memory>

// Behind the recovery screen, shown instead of the app when plotter.db cannot be opened.
// startFresh() moves the bad file aside (plotter.db, -wal, -shm) and opens a new one. It never
// reopens the bad file: if any of the three is still in place after the move, it stops and says so.
class Recovery : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString reason READ reason CONSTANT)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(bool canRetry READ canRetry CONSTANT)

public:
    Recovery(QString dir, StoreError error, QObject* parent = nullptr);

    QString reason() const { return m_reason; }
    QString error() const { return m_error; }
    // Io errors may pass (a disk not ready yet): the screen also offers opening the same file again.
    bool canRetry() const { return m_canRetry; }
    // Where the bad file went (empty when there was nothing to move).
    QString movedTo() const { return m_movedTo; }
    // The opened store once recovered() was emitted; null before.
    std::unique_ptr<Store> takeStore() { return std::move(m_store); }

    Q_INVOKABLE void startFresh();
    Q_INVOKABLE void retry();

signals:
    void errorChanged();
    void recovered();

private:
    void setError(const QString& e);
    void take(std::expected<std::unique_ptr<Store>, StoreError> r);

    QString m_dir;
    QString m_reason;
    QString m_error;
    bool m_canRetry;
    QString m_movedTo;
    std::unique_ptr<Store> m_store;
};

// The recovery screen's text for a store error.
QString storeErrorReason(StoreError e);
