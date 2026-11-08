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

// Top-down Hewescraft in a 40 x 100 box (boat-icon-v3.html, style C), box height = lengthPx, centered on
// a square canvas. Strokes are in box units with a 1 px floor.
QImage boat(double lengthPx, const OverlayColours& c) {
    const int len = std::max(8, int(std::lround(lengthPx)));
    const double s = len / 100.0;
    const auto w = [s](double units) { return std::max(units, 1.0 / s); };
    QImage img(len, len, QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing);
    p.translate((len - 40.0 * s) / 2.0, 0);
    p.scale(s, s);
    const auto stroked = [&](double units, const QColor& pen) {
        p.setPen(QPen(pen, w(units), Qt::SolidLine, Qt::FlatCap, Qt::MiterJoin));
    };
    stroked(1, c.motorOutline);
    p.setBrush(c.motor);
    p.drawRect(QRectF(15.5, 88, 9, 9));
    stroked(0.8, c.motorOutline);
    p.drawRect(QRectF(27, 88, 4.5, 6));

    QPainterPath hull;
    hull.moveTo(20, 3);
    hull.cubicTo(29, 14, 34, 28, 34, 40);
    hull.lineTo(34, 88);
    hull.lineTo(6, 88);
    hull.lineTo(6, 40);
    hull.cubicTo(6, 28, 11, 14, 20, 3);
    hull.closeSubpath();
    stroked(2, c.hullOutline);
    p.setBrush(c.hullFill);
    p.drawPath(hull);

    stroked(1, c.hullOutline);
    p.setBrush(c.cabin);
    p.drawRoundedRect(QRectF(10, 36, 20, 28), 3, 3);

    p.setPen(Qt::NoPen);
    QPainterPath ws;
    ws.moveTo(11, 40);
    ws.quadTo(20, 34, 29, 40);
    ws.lineTo(29, 44);
    ws.quadTo(20, 39, 11, 44);
    ws.closeSubpath();
    p.setBrush(c.windshield);
    p.drawPath(ws);

    QPainterPath port, stbd;
    port.moveTo(10, 37.5);
    port.arcTo(QRectF(6.5, 37.5, 7, 7), 90, 180);
    port.closeSubpath();
    stbd.moveTo(30, 37.5);
    stbd.arcTo(QRectF(26.5, 37.5, 7, 7), 90, -180);
    stbd.closeSubpath();
    p.setBrush(c.portLight);
    p.drawPath(port);
    p.setBrush(c.stbdLight);
    p.drawPath(stbd);
    return img;
}

// A bar lengthPx long and 3 px thick (like the cm-own-cog line), horizontal and centered on a square
// canvas; rotated by the COG it lies across the line.
QImage cogTip(double lengthPx, const OverlayColours& c) {
    const int len = std::max(4, int(std::lround(lengthPx)));
    QImage img(len, len, QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(Qt::NoPen);
    p.setBrush(c.cog);
    p.drawRect(QRectF(0, (len - 3.0) / 2.0, len, 3.0));
    return img;
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
        {OverlayIds::kBoatImage, boat(9 * pxPerMm, colours)},
        {OverlayIds::kAisImageA, triangle(6 * pxPerMm, outline, colours, true)},
        {OverlayIds::kAisImageB, triangle(4.5 * pxPerMm, outline, colours, true)},
        {OverlayIds::kAisImageHollow, triangle(6 * pxPerMm, outline, colours, false)},
        {OverlayIds::kCogTipImage, cogTip(4 * pxPerMm, colours)},
    };
}
