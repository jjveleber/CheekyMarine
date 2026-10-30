#pragma once
#include <QEvent>
#include <QObject>
#include <functional>

// The touch lock state machine, with an injectable clock (milliseconds). Locks on lockNow() or when
// the idle time reaches timeoutS (0 = never by idle); unlocks by a hold of kHoldMs on the lock icon.
// poll() does the time-based work; production calls it every kPollMs.
class TouchLock : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool locked READ locked NOTIFY lockedChanged)
    Q_PROPERTY(double holdProgress READ holdProgress NOTIFY holdProgressChanged)
    Q_PROPERTY(int timeoutS READ timeoutS WRITE setTimeoutS NOTIFY timeoutSChanged)

public:
    static constexpr qint64 kHoldMs = 1500;
    static constexpr int kPollMs = 100;

    explicit TouchLock(std::function<qint64()> nowMs, QObject* parent = nullptr);

    bool locked() const { return m_locked; }
    double holdProgress() const { return m_progress; }
    int timeoutS() const { return m_timeoutS; }
    void setTimeoutS(int s);

public slots:
    void activity();  // a touch while unlocked; ignored while locked
    void lockNow();
    void holdStart(); // the finger went down on the lock icon (locked only)
    void holdEnd();
    void poll();

signals:
    void lockedChanged();
    void holdProgressChanged();
    void timeoutSChanged();

private:
    void setLocked(bool v);
    void setProgress(double p);

    std::function<qint64()> m_now;
    bool m_locked = false;
    bool m_holding = false;
    double m_progress = 0;
    int m_timeoutS = 0;
    qint64 m_lastActivity = 0;
    qint64 m_holdStarted = 0;
};

// Installed on the application window: any touch, mouse or wheel event is activity for the lock.
// Never consumes an event (the overlay does the swallowing while locked).
class TouchActivityFilter : public QObject {
    Q_OBJECT

public:
    TouchActivityFilter(TouchLock* lock, QObject* parent) : QObject(parent), m_lock(lock) {}

protected:
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    TouchLock* m_lock;
};
