#pragma once
#include "core/SpriteSheet.h"
#include <QQuickImageProvider>
#include <functional>
#include <optional>

// The legend's symbols, registered as image provider "legend" (synchronous, so it runs on the GUI
// thread only). Ids:
// - sprite/<name>/<tint>: entry `name` of the charts pack sprite sheet at `spriteBase()` (reloaded
//   when that changes), SDF entries tinted with color <tint> (hex without '#') or black for "none".
//   Drawn at its map size in logical px (entry px / the sheet's pixel ratio), or at the requested size.
// - overlay/<id>/<palette>: chartIcons() image `id` for `palette`, at `pxPerMm()`.
// Anything else, or an unreadable sheet, gives a fully transparent 1 x 1 image: a null image would be
// a load error (and a warning) in QML.
class LegendImageProvider : public QQuickImageProvider {
public:
    LegendImageProvider(std::function<QString()> spriteBase, std::function<double()> pxPerMm);
    QImage requestImage(const QString& id, QSize* size, const QSize& requestedSize) override;

private:
    QImage sprite(const QString& name, const QString& tint, QSize* size, const QSize& requestedSize);
    std::function<QString()> m_spriteBase;
    std::function<double()> m_pxPerMm;
    std::optional<QString> m_loadedBase; // the base m_sheet was loaded from, set even if that failed
    std::optional<SpriteSheet> m_sheet;
    int m_pixelRatio = 1;
};
