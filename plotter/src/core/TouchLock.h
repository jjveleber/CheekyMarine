#pragma once
#include <QObject>
#include <functional>

class QTimer;

// The touch lock state machine, with an injectable clock (milliseconds). Locks on lockNow(); unlocks
// by a hold of kHoldMs on the lock icon. poll() advances the hold; production calls it every kPollMs.
class TouchLock : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool locked READ locked NOTIFY lockedChanged)
    Q_PROPERTY(double holdProgress READ holdProgress NOTIFY holdProgressChanged)

public:
    static constexpr qint64 kHoldMs = 1500;
    static constexpr int kPollMs = 100;

    explicit TouchLock(std::function<qint64()> nowMs, QObject* parent = nullptr);

    bool locked() const { return m_locked; }
    double holdProgress() const { return m_progress; }

public slots:
    void lockNow();
    void holdStart(); // the finger went down on the lock icon (locked only)
    void holdEnd();
    void poll();

signals:
    void lockedChanged();
    void holdProgressChanged();

private:
    void setLocked(bool v);
    void setProgress(double p);

    std::function<qint64()> m_now;
    bool m_locked = false;
    bool m_holding = false;
    double m_progress = 0;
    qint64 m_holdStarted = 0;
};

// Makes `timer` call lock.poll() every kPollMs, running only while the lock is on (a hold needs it).
// Both must outlive the connection.
void pollWhileNeeded(TouchLock& lock, QTimer& timer);
