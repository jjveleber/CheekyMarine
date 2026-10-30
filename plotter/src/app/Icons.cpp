#include "app/Icons.h"
#include "core/Overlays.h"

#include <QPainter>
#include <QPainterPath>
#include <algorithm>
#include <cmath>

namespace {
const QColor kFill(255, 210, 0);
const QColor kOutline(Qt::black);

// A square canvas of side `len` so that icon-rotate turns the shape about its centre.
QImage draw(int len, double outlinePx, const QPainterPath& path, bool filled) {
    QImage img(len, len, QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(QPen(kOutline, outlinePx, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    p.setBrush(filled ? QBrush(kFill) : QBrush(Qt::NoBrush));
    p.drawPath(path);
    return img;
}

QImage boat(double lengthPx, double outlinePx) {
    const int len = std::max(8, int(std::lround(lengthPx)));
    const double c = len / 2.0, m = outlinePx; // keep the outline inside the canvas
    QPainterPath hull;
    hull.moveTo(c, m);
    hull.quadTo(c + 0.30 * len, 0.30 * len, c + 0.22 * len, len - m);
    hull.lineTo(c - 0.22 * len, len - m);
    hull.quadTo(c - 0.30 * len, 0.30 * len, c, m);
    return draw(len, outlinePx, hull, true);
}

QImage triangle(double lengthPx, double outlinePx, bool filled) {
    const int len = std::max(6, int(std::lround(lengthPx)));
    const double c = len / 2.0, m = outlinePx;
    QPainterPath t;
    t.moveTo(c, m);
    t.lineTo(c + 0.30 * len, len - m);
    t.lineTo(c - 0.30 * len, len - m);
    t.closeSubpath();
    return draw(len, outlinePx, t, filled);
}
} // namespace

QHash<QString, QImage> chartIcons(double pxPerMm) {
    const double outline = std::max(2.0, 0.4 * pxPerMm);
    return {
        {OverlayIds::kBoatImage, boat(12 * pxPerMm, outline)},
        {OverlayIds::kAisImageA, triangle(8 * pxPerMm, outline, true)},
        {OverlayIds::kAisImageB, triangle(6 * pxPerMm, outline, true)},
        {OverlayIds::kAisImageHollow, triangle(8 * pxPerMm, outline, false)},
    };
}
