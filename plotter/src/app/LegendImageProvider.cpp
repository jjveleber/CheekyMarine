#include "app/LegendImageProvider.h"
#include "app/Icons.h"

#include <QDebug>
#include <QFile>
#include <cmath>

namespace {
QImage blank(QSize* size) {
    QImage img(1, 1, QImage::Format_ARGB32);
    img.fill(Qt::transparent);
    if (size) *size = img.size();
    return img;
}
// A requested size (QML sourceSize) only counts with both sides set.
bool wanted(const QSize& s) { return s.width() > 0 && s.height() > 0; }
} // namespace

LegendImageProvider::LegendImageProvider(std::function<QString()> spriteBase, std::function<double()> pxPerMm)
    : QQuickImageProvider(QQuickImageProvider::Image), m_spriteBase(std::move(spriteBase)),
      m_pxPerMm(std::move(pxPerMm)) {}

QImage LegendImageProvider::requestImage(const QString& id, QSize* size, const QSize& requestedSize) {
    const QStringList parts = id.split(QLatin1Char('/'));
    if (parts.size() != 3) return blank(size);
    if (parts[0] == QLatin1String("sprite")) return sprite(parts[1], parts[2], size, requestedSize);
    if (parts[0] == QLatin1String("overlay")) {
        const QImage img = chartIcons(m_pxPerMm(), parts[2]).value(parts[1]);
        if (img.isNull()) return blank(size);
        if (size) *size = img.size();
        return wanted(requestedSize) ? img.scaled(requestedSize, Qt::IgnoreAspectRatio, Qt::SmoothTransformation)
                                       : img;
    }
    return blank(size);
}

QImage LegendImageProvider::sprite(const QString& name, const QString& tint, QSize* size, const QSize& requestedSize) {
    const QString base = m_spriteBase();
    if (m_loadedBase != base) {
        m_loadedBase = base;
        m_sheet.reset();
        if (!base.isEmpty()) {
            auto sheet = SpriteSheet::load(base);
            if (sheet) {
                m_sheet = std::move(*sheet);
                // SpriteSheet::load prefers @2x the same way.
                m_pixelRatio = QFile::exists(base + "@2x.json") && QFile::exists(base + "@2x.png") ? 2 : 1;
            } else {
                qWarning().noquote() << "legend: no sprite images," << sheet.error();
            }
        }
    }
    if (!m_sheet) return blank(size);
    std::optional<QColor> color;
    if (tint != QLatin1String("none")) {
        const QColor c = QColor::fromString(QLatin1Char('#') + tint);
        if (!c.isValid()) return blank(size);
        color = c;
    }
    const QImage img = m_sheet->image(name, color);
    if (img.isNull()) return blank(size);
    const QSize logical(int(std::lround(img.width() / double(m_pixelRatio))),
                        int(std::lround(img.height() / double(m_pixelRatio))));
    if (size) *size = logical;
    const QSize out = wanted(requestedSize) ? requestedSize : logical;
    return out == img.size() ? img : img.scaled(out, Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
}
