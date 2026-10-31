#include "core/TouchLock.h"
#include <QTimer>
#include <algorithm>

TouchLock::TouchLock(std::function<qint64()> nowMs, QObject* parent)
    : QObject(parent), m_now(std::move(nowMs)), m_lastActivity(m_now()) {}

void TouchLock::setTimeoutS(int s) {
    s = std::max(0, s);
    if (s == m_timeoutS) return;
    m_timeoutS = s;
    emit timeoutSChanged();
}

void TouchLock::activity() {
    if (!m_locked) m_lastActivity = m_now();
}

void TouchLock::lockNow() {
    m_holding = false;
    setProgress(0);
    setLocked(true);
}

void TouchLock::holdStart() {
    if (!m_locked) return;
    m_holding = true;
    m_holdStarted = m_now();
    setProgress(0);
}

void TouchLock::holdEnd() {
    m_holding = false;
    setProgress(0);
}

void TouchLock::poll() {
    const qint64 now = m_now();
    if (!m_locked) {
        if (m_timeoutS > 0 && now - m_lastActivity >= qint64(m_timeoutS) * 1000) lockNow();
        return;
    }
    if (!m_holding) return;
    const qint64 held = now - m_holdStarted;
    if (held >= kHoldMs) {
        m_holding = false;
        m_lastActivity = now;
        setProgress(0);
        setLocked(false);
    } else {
        setProgress(double(held) / kHoldMs);
    }
}

void TouchLock::setLocked(bool v) {
    if (v == m_locked) return;
    m_locked = v;
    emit lockedChanged();
}

void TouchLock::setProgress(double p) {
    if (p == m_progress) return;
    m_progress = p;
    emit holdProgressChanged();
}

void pollWhileNeeded(TouchLock& lock, QTimer& timer) {
    timer.setInterval(TouchLock::kPollMs);
    QObject::connect(&timer, &QTimer::timeout, &lock, &TouchLock::poll);
    const auto update = [&lock, &timer] {
        if (lock.timeoutS() == 0 && !lock.locked())
            timer.stop();
        else if (!timer.isActive())
            timer.start();
    };
    QObject::connect(&lock, &TouchLock::lockedChanged, &timer, update);
    QObject::connect(&lock, &TouchLock::timeoutSChanged, &timer, update);
    update();
}

bool TouchActivityFilter::eventFilter(QObject* watched, QEvent* event) {
    switch (event->type()) {
    case QEvent::MouseButtonPress:
    case QEvent::MouseMove:
    case QEvent::MouseButtonRelease:
    case QEvent::TouchBegin:
    case QEvent::TouchUpdate:
    case QEvent::TouchEnd:
    case QEvent::Wheel:
        m_lock->activity();
        break;
    default:
        break;
    }
    return QObject::eventFilter(watched, event);
}
