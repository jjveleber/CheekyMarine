#include "app/Icons.h"
#include "core/Overlays.h"

#include <QPainter>
#include <QPainterPath>
#include <algorithm>
#include <cmath>
#include <optional>

namespace {
// A square canvas of side `len` so that icon-rotate turns the shape about its centre. Without a
// fill the shape is hollow.
QImage draw(int len, double outlinePx, const QPainterPath& path, const QColor& outline,
            const std::optional<QColor>& fill) {
    QImage img(len, len, QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(QPen(outline, outlinePx, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    p.setBrush(fill ? QBrush(*fill) : QBrush(Qt::NoBrush));
    p.drawPath(path);
    return img;
}

QImage boat(double lengthPx, double outlinePx, const OverlayColours& colours) {
    const int len = std::max(8, int(std::lround(lengthPx)));
    const double c = len / 2.0, m = outlinePx; // keep the outline inside the canvas
    QPainterPath hull;
    hull.moveTo(c, m);
    hull.quadTo(c + 0.30 * len, 0.30 * len, c + 0.22 * len, len - m);
    hull.lineTo(c - 0.22 * len, len - m);
    hull.quadTo(c - 0.30 * len, 0.30 * len, c, m);
    return draw(len, outlinePx, hull, colours.boatOutline, colours.boatFill);
}

QImage triangle(double lengthPx, double outlinePx, const OverlayColours& colours, bool filled) {
    const int len = std::max(6, int(std::lround(lengthPx)));
    const double c = len / 2.0, m = outlinePx;
    QPainterPath t;
    t.moveTo(c, m);
    t.lineTo(c + 0.30 * len, len - m);
    t.lineTo(c - 0.30 * len, len - m);
    t.closeSubpath();
    return draw(len, outlinePx, t, colours.aisOutline,
                filled ? std::optional<QColor>(colours.aisFill) : std::nullopt);
}
} // namespace

QHash<QString, QImage> chartIcons(double pxPerMm, const QString& palette) {
    const OverlayColours colours = overlayColours(palette);
    const double outline = std::max(2.0, 0.4 * pxPerMm);
    return {
        {OverlayIds::kBoatImage, boat(12 * pxPerMm, outline, colours)},
        {OverlayIds::kAisImageA, triangle(8 * pxPerMm, outline, colours, true)},
        {OverlayIds::kAisImageB, triangle(6 * pxPerMm, outline, colours, true)},
        {OverlayIds::kAisImageHollow, triangle(8 * pxPerMm, outline, colours, false)},
    };
}
