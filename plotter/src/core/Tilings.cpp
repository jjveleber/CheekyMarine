#include "core/Tilings.h"
#include <QVariantMap>
#include <algorithm>

namespace {

bool supportedGrid(int cols, int rows)
{
    return (cols == 2 && rows == 2) || (cols == 2 && rows == 3) || (cols == 3 && rows == 2);
}

// Plain ASCII digits only: toInt alone would also accept a sign or surrounding spaces.
std::optional<int> plainInt(QStringView s)
{
    if (s.isEmpty() || !std::all_of(s.begin(), s.end(), [](QChar c) { return c >= u'0' && c <= u'9'; }))
        return std::nullopt;
    bool ok = false;
    const int v = s.toInt(&ok);
    return ok ? std::optional<int>(v) : std::nullopt;
}

bool readingOrderLess(const CellRect& a, const CellRect& b)
{
    return a.row != b.row ? a.row < b.row : a.col < b.col;
}

void generate(int cols, int rows, QList<bool>& covered, QList<CellRect>& cells, QList<Layout>& out)
{
    int first = 0;
    while (first < covered.size() && covered[first])
        ++first;
    if (first == covered.size()) {
        out.append({cols, rows, cells});
        return;
    }
    const int col = first % cols, row = first / cols;
    for (int rowSpan = 1; row + rowSpan <= rows; ++rowSpan) {
        for (int colSpan = 1; col + colSpan <= cols; ++colSpan) {
            bool free = true;
            for (int r = row; r < row + rowSpan && free; ++r)
                for (int c = col; c < col + colSpan && free; ++c)
                    free = !covered[r * cols + c];
            if (!free)
                continue;
            for (int r = row; r < row + rowSpan; ++r)
                for (int c = col; c < col + colSpan; ++c)
                    covered[r * cols + c] = true;
            cells.append({col, row, colSpan, rowSpan});
            generate(cols, rows, covered, cells, out);
            cells.removeLast();
            for (int r = row; r < row + rowSpan; ++r)
                for (int c = col; c < col + colSpan; ++c)
                    covered[r * cols + c] = false;
        }
    }
}

int gridRank(const Layout& l)
{
    return l.cols == 2 && l.rows == 2 ? 0 : (l.cols == 2 ? 1 : 2);
}

QList<Layout> buildAll()
{
    QList<Layout> all;
    for (const auto& [cols, rows] : {std::pair{2, 2}, std::pair{2, 3}, std::pair{3, 2}})
        for (const Layout& l : tilings(cols, rows)) {
            const bool seen = std::any_of(all.cbegin(), all.cend(), [&](const Layout& k) { return sameShape(k, l); });
            if (!seen)
                all.append(l);
        }
    std::sort(all.begin(), all.end(), [](const Layout& a, const Layout& b) {
        if (a.cells.size() != b.cells.size())
            return a.cells.size() < b.cells.size();
        if (gridRank(a) != gridRank(b))
            return gridRank(a) < gridRank(b);
        return layoutKey(a) < layoutKey(b);
    });
    return all;
}

} // namespace

QList<Layout> tilings(int cols, int rows)
{
    QList<Layout> out;
    QList<bool> covered(cols * rows, false);
    QList<CellRect> cells;
    generate(cols, rows, covered, cells, out);
    return out;
}

QString layoutKey(const Layout& l)
{
    QStringList parts;
    for (const CellRect& c : l.cells)
        parts << QStringLiteral("%1,%2,%3,%4").arg(c.col).arg(c.row).arg(c.colSpan).arg(c.rowSpan);
    return QStringLiteral("%1x%2:").arg(l.cols).arg(l.rows) + parts.join(u';');
}

std::optional<Layout> layoutFromKey(QStringView key)
{
    const qsizetype colon = key.indexOf(u':');
    if (colon < 0)
        return std::nullopt;
    const QList<QStringView> dims = key.left(colon).split(u'x');
    if (dims.size() != 2)
        return std::nullopt;
    const auto cols = plainInt(dims[0]), rows = plainInt(dims[1]);
    if (!cols || !rows || !supportedGrid(*cols, *rows))
        return std::nullopt;
    Layout l{*cols, *rows, {}};
    QList<int> covered(l.cols * l.rows, 0);
    for (const QStringView part : key.mid(colon + 1).split(u';')) {
        const QList<QStringView> f = part.split(u',');
        if (f.size() != 4)
            return std::nullopt;
        int v[4];
        for (int i = 0; i < 4; ++i) {
            const auto n = plainInt(f[i]);
            if (!n)
                return std::nullopt;
            v[i] = *n;
        }
        const CellRect c{v[0], v[1], v[2], v[3]};
        if (c.col >= l.cols || c.row >= l.rows || c.colSpan < 1 || c.rowSpan < 1 || c.colSpan > l.cols - c.col
            || c.rowSpan > l.rows - c.row)
            return std::nullopt;
        for (int r = c.row; r < c.row + c.rowSpan; ++r)
            for (int k = c.col; k < c.col + c.colSpan; ++k)
                if (++covered[r * l.cols + k] > 1)
                    return std::nullopt;
        l.cells.append(c);
    }
    if (std::find(covered.cbegin(), covered.cend(), 0) != covered.cend())
        return std::nullopt;
    std::sort(l.cells.begin(), l.cells.end(), readingOrderLess);
    return l;
}

bool sameShape(const Layout& a, const Layout& b)
{
    if (a.cells.size() != b.cells.size())
        return false;
    for (qsizetype i = 0; i < a.cells.size(); ++i) {
        const CellRect &p = a.cells[i], &q = b.cells[i];
        if (p.col * b.cols != q.col * a.cols || p.colSpan * b.cols != q.colSpan * a.cols
            || p.row * b.rows != q.row * a.rows || p.rowSpan * b.rows != q.rowSpan * a.rows)
            return false;
    }
    return true;
}

const QList<Layout>& allLayouts()
{
    static const QList<Layout> all = buildAll();
    return all;
}

QString canonicalKey(const Layout& l)
{
    for (const Layout& k : allLayouts())
        if (sameShape(k, l))
            return layoutKey(k);
    return {};
}

QVariantList layoutRects(const Layout& l)
{
    QVariantList out;
    for (const CellRect& c : l.cells)
        out.append(QVariantMap{{"x", double(c.col) / l.cols},
                               {"y", double(c.row) / l.rows},
                               {"w", double(c.colSpan) / l.cols},
                               {"h", double(c.rowSpan) / l.rows}});
    return out;
}
