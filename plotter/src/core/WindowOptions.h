#pragma once

#include <QSize>
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
