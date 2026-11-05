#pragma once

#include <QList>
#include <QSize>
#include <QString>
#include <algorithm>
#include <QWindow>

// Applies the command-line window options to the already shown main window.
// Fullscreen wins and ignores size; otherwise a valid size resizes the window.
inline void applyWindowOptions(QWindow& w, bool fullscreen, QSize size) {
    if (fullscreen) {
        w.showFullScreen();
        return;
    }
    if (size.isValid()) w.resize(size);
}

namespace detail {
struct StatsSummary {
    qsizetype n = 0;
    qint64 max = 0;
    qint64 p99 = 0; // nearest rank
    qsizetype over = 0;
};
inline StatsSummary summarize(const QList<qint64>& values, qint64 overLimit) {
    QList<qint64> sorted = values;
    std::sort(sorted.begin(), sorted.end());
    StatsSummary s;
    s.n = sorted.size();
    s.max = s.n ? sorted.last() : 0;
    s.p99 = s.n ? sorted[(99 * s.n + 99) / 100 - 1] : 0;
    s.over = std::count_if(sorted.begin(), sorted.end(), [overLimit](qint64 v) { return v > overLimit; });
    return s;
}
} // namespace detail

// The --frame-stats summary of the intervals (ms) between consecutive frames: the count, the
// longest, the 99th percentile (nearest rank) and how many exceeded 50 ms.
inline QString frameStatsLine(const QList<qint64>& intervalsMs) {
    const auto s = detail::summarize(intervalsMs, 50);
    return QStringLiteral("frame-stats: frames %1 max %2 ms p99 %3 ms over50 %4").arg(s.n).arg(s.max).arg(s.p99).arg(s.over);
}

// The --frame-stats summary of the main-thread time (us) inside each active-track write, in ms: the
// count, the longest, the 99th percentile and how many exceeded 50 ms.
inline QString writeStatsLine(const QList<qint64>& writesUs) {
    const auto s = detail::summarize(writesUs, 50000);
    return QStringLiteral("track-writes: writes %1 max %2 ms p99 %3 ms over50 %4")
        .arg(s.n)
        .arg(s.max / 1000.0, 0, 'f', 2)
        .arg(s.p99 / 1000.0, 0, 'f', 2)
        .arg(s.over);
}
