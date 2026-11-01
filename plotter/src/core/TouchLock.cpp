#include "core/TouchLock.h"
#include <QTimer>

TouchLock::TouchLock(std::function<qint64()> nowMs, QObject* parent)
    : QObject(parent), m_now(std::move(nowMs)) {}

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
    if (!m_locked || !m_holding) return;
    const qint64 held = m_now() - m_holdStarted;
    if (held >= kHoldMs) {
        m_holding = false;
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
        if (!lock.locked())
            timer.stop();
        else if (!timer.isActive())
            timer.start();
    };
    QObject::connect(&lock, &TouchLock::lockedChanged, &timer, update);
    update();
}
