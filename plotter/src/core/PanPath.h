#pragma once
#include <QList>
#include <QString>
#include <expected>

// Dev option --pan-path: waypoints the camera pans through, the same way every run.
struct PanPoint {
    double lat, lon, zoom;
};

// "lat,lon,zoom;lat,lon,zoom;..." with at least two points.
std::expected<QList<PanPoint>, QString> parsePanPath(const QString& text);

// The camera `tMs` after the start: linear in lat, lon and zoom along each leg of `legMs`, and after
// the last point the path loops back to the first. `path` needs at least two points, `legMs` > 0.
PanPoint panAt(const QList<PanPoint>& path, qint64 legMs, qint64 tMs);
