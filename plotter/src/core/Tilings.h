#pragma once

#include <QList>
#include <QString>
#include <QStringView>
#include <QVariantList>
#include <optional>

// Saved-view cell layouts: a 2x2, 2x3 or 3x2 grid tiled exactly by rectangles of cells.
struct CellRect {
    int col, row, colSpan, rowSpan;
    bool operator==(const CellRect&) const = default;
};

struct Layout {
    int cols, rows;
    QList<CellRect> cells; // reading order: by row, then col, of the top-left corner
    bool operator==(const Layout&) const = default;
};

// "<cols>x<rows>:<col>,<row>,<colSpan>,<rowSpan>;..." with cells in reading order.
QString layoutKey(const Layout&);
// nullopt unless the grid is 2x2, 2x3 or 3x2 and the rectangles tile it exactly.
std::optional<Layout> layoutFromKey(QStringView);
// Equal as fractions of their grids.
bool sameShape(const Layout&, const Layout&);
// The 72 distinct shapes, ordered by cell count, then grid (2x2, 2x3, 3x2), then key.
const QList<Layout>& allLayouts();
// Key of the allLayouts() entry with the same shape (empty when none).
QString canonicalKey(const Layout&);
// [{x, y, w, h}] as fractions 0 to 1, in cell order.
QVariantList layoutRects(const Layout&);
// One grid's complete tiling list, before deduplication across grids.
QList<Layout> tilings(int cols, int rows);
