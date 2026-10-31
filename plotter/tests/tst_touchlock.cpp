#include "core/MonotonicClock.h"
#include "core/TouchLock.h"
#include <QThread>
#include <QTimer>
#include <QtGui/QMouseEvent>
#include <QtTest>

class TstTouchLock : public QObject {
    Q_OBJECT
    qint64 now = 1000000;

private slots:
    void init() { now = 1000000; }

    void locksAtTimeout() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(120);
        now += 119900;
        l.poll();
        QVERIFY(!l.locked());
        now += 100;
        l.poll();
        QVERIFY(l.locked());
    }
    void activityPushesTheTimeout() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(120);
        now += 100000;
        l.activity();
        now += 119900;
        l.poll();
        QVERIFY(!l.locked());
        now += 100;
        l.poll();
        QVERIFY(l.locked());
    }
    void activityIgnoredWhileLocked() {
        TouchLock l([this] { return now; });
        l.lockNow();
        QVERIFY(l.locked());
        l.activity();
        QVERIFY(l.locked());
    }
    void timeoutZeroNeverLocks() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(0);
        now += 10000000;
        l.poll();
        QVERIFY(!l.locked());
    }
    void holdUnlocksAt1500() {
        TouchLock l([this] { return now; });
        l.lockNow();
        l.holdStart();
        now += 1499;
        l.poll();
        QVERIFY(l.locked());
        QVERIFY(l.holdProgress() > 0.99 && l.holdProgress() < 1.0);
        now += 1;
        l.poll();
        QVERIFY(!l.locked());
        QCOMPARE(l.holdProgress(), 0.0);
    }
    void unlockResetsIdleClock() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(30);
        l.lockNow();
        now += 100000;
        l.holdStart();
        now += 1500;
        l.poll();
        QVERIFY(!l.locked());
        now += 29900;
        l.poll();
        QVERIFY(!l.locked());
        now += 100;
        l.poll();
        QVERIFY(l.locked());
    }
    void earlyReleaseResets() {
        TouchLock l([this] { return now; });
        l.lockNow();
        l.holdStart();
        now += 1000;
        l.poll();
        QVERIFY(l.holdProgress() > 0);
        l.holdEnd();
        QCOMPARE(l.holdProgress(), 0.0);
        now += 1000;
        l.poll();
        QVERIFY(l.locked());
        QCOMPARE(l.holdProgress(), 0.0);
    }
    void holdWhileUnlockedDoesNothing() {
        TouchLock l([this] { return now; });
        l.holdStart();
        now += 2000;
        l.poll();
        QVERIFY(!l.locked());
        QCOMPARE(l.holdProgress(), 0.0);
    }
    void lockNowLocksAtOnce() {
        TouchLock l([this] { return now; });
        QSignalSpy spy(&l, &TouchLock::lockedChanged);
        l.lockNow();
        QVERIFY(l.locked());
        QCOMPARE(spy.count(), 1);
    }

    // The clock main.cpp gives the lock is Qt's monotonic clock, not the wall clock, which steps
    // when NTP or GNSS time corrects it (no RTC on the Pi): it never goes back and counts real time.
    void productionClockIsMonotonic() {
        QCOMPARE(QElapsedTimer::clockType(), QElapsedTimer::MonotonicClock);
        const auto clock = monotonicMsClock();
        const qint64 start = clock();
        QVERIFY(start >= 0 && start < 1000);
        qint64 prev = start;
        for (int i = 0; i < 1000; ++i) {
            const qint64 t = clock();
            QVERIFY(t >= prev);
            prev = t;
        }
        QThread::msleep(50);
        QVERIFY(clock() - start >= 45);
    }
    // The 100 ms poll runs only while it can change something: a timeout is set, or the lock is on
    // (a hold in progress needs it).
    void pollTimerRunsOnlyWhileTimeoutSetOrLocked() {
        TouchLock l([this] { return now; });
        QTimer timer;
        pollWhileNeeded(l, timer);
        QCOMPARE(timer.interval(), TouchLock::kPollMs);
        QVERIFY(!timer.isActive()); // timeout off, unlocked
        l.setTimeoutS(30);
        QVERIFY(timer.isActive());
        l.setTimeoutS(0);
        QVERIFY(!timer.isActive());
        l.lockNow();
        QVERIFY(timer.isActive());
        // The timer drives poll(): a completed hold unlocks without anyone calling poll().
        l.holdStart();
        now += TouchLock::kHoldMs;
        QTRY_VERIFY_WITH_TIMEOUT(!l.locked(), 2000);
        QVERIFY(!timer.isActive()); // unlocked with the timeout off again
    }

    void filterReportsInputAsActivity() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(30);
        QObject window;
        window.installEventFilter(new TouchActivityFilter(&l, &window));
        now += 29000;
        QMouseEvent press(QEvent::MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt::LeftButton, Qt::LeftButton,
                          Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &press);
        now += 29000;
        l.poll();
        QVERIFY(!l.locked()); // the press at 29 s restarted the idle time
        now += 1000;
        l.poll();
        QVERIFY(l.locked());
        // Locked: input does not matter, and the filter does not eat it.
        QMouseEvent move(QEvent::MouseMove, QPointF(5, 5), QPointF(5, 5), Qt::NoButton, Qt::NoButton, Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &move);
        QVERIFY(l.locked());
    }
    void filterIgnoresOtherEvents() {
        TouchLock l([this] { return now; });
        l.setTimeoutS(30);
        QObject window;
        window.installEventFilter(new TouchActivityFilter(&l, &window));
        now += 29000;
        QEvent other(QEvent::Timer);
        QCoreApplication::sendEvent(&window, &other);
        now += 1000;
        l.poll();
        QVERIFY(l.locked());
    }
};

QTEST_GUILESS_MAIN(TstTouchLock)
#include "tst_touchlock.moc"
