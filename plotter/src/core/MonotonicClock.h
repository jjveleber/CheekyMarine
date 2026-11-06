#pragma once
#include <QElapsedTimer>
#include <ctime>
#include <functional>
#include <memory>

// The clocks main.cpp gives the touch lock and the track recorder: Qt's monotonic clock, counted
// from the call that made them. The Pi has no RTC, so the wall clock steps when NTP or GNSS time
// corrects it; these never do.
inline std::function<qint64()> monotonicMsClock() {
    auto timer = std::make_shared<QElapsedTimer>();
    timer->start();
    return [timer] { return timer->elapsed(); };
}

inline std::function<double()> monotonicSecondsClock() {
    auto timer = std::make_shared<QElapsedTimer>();
    timer->start();
    return [timer] { return double(timer->nsecsElapsed()) / 1e9; };
}

// The recorder's clock: CLOCK_BOOTTIME (Linux) in seconds, which counts time the machine spends
// suspended (so a long sleep is a gap and starts a new track) and, like the clocks above, never
// steps with the wall clock.
inline std::function<double()> boottimeSecondsClock() {
    return [] {
        timespec ts{};
        clock_gettime(CLOCK_BOOTTIME, &ts);
        return double(ts.tv_sec) + double(ts.tv_nsec) / 1e9;
    };
}
