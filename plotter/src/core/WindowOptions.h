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

// The --frame-stats summary of the intervals (ms) between consecutive frames: the count, the
// longest, the 99th percentile (nearest rank) and how many exceeded 50 ms.
inline QString frameStatsLine(const QList<qint64>& intervalsMs) {
    QList<qint64> sorted = intervalsMs;
    std::sort(sorted.begin(), sorted.end());
    const qsizetype n = sorted.size();
    const qint64 max = n ? sorted.last() : 0;
    const qint64 p99 = n ? sorted[(99 * n + 99) / 100 - 1] : 0;
    const qsizetype over = std::count_if(sorted.begin(), sorted.end(), [](qint64 v) { return v > 50; });
    return QStringLiteral("frame-stats: frames %1 max %2 ms p99 %3 ms over50 %4").arg(n).arg(max).arg(p99).arg(over);
}
