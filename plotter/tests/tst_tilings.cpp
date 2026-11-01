#include "core/Tilings.h"
#include <QtTest>
#include <QSet>

class TstTilings : public QObject {
    Q_OBJECT
private slots:
    void perGridCounts()
    {
        QCOMPARE(tilings(2, 2).size(), 8);
        QCOMPARE(tilings(2, 3).size(), 34);
        QCOMPARE(tilings(3, 2).size(), 34);
    }
    void seventyTwoDistinctShapes()
    {
        const auto& all = allLayouts();
        QCOMPARE(all.size(), 72);
        int ones = 0, most = 0;
        QSet<QString> keys;
        for (const Layout& l : all) {
            if (l.cells.size() == 1)
                ++ones;
            most = qMax(most, int(l.cells.size()));
            keys.insert(layoutKey(l));
            QCOMPARE(canonicalKey(l), layoutKey(l));
        }
        QCOMPARE(ones, 1);
        QCOMPARE(most, 6);
        QCOMPARE(keys.size(), 72);
    }
    void everyShapeIsACompleteTiling()
    {
        for (const Layout& l : allLayouts()) {
            QList<int> grid(l.cols * l.rows, 0);
            int area = 0, prevRow = -1, prevCol = -1;
            for (const CellRect& c : l.cells) {
                area += c.colSpan * c.rowSpan;
                QVERIFY(c.col >= 0 && c.row >= 0 && c.colSpan >= 1 && c.rowSpan >= 1);
                QVERIFY(c.col + c.colSpan <= l.cols && c.row + c.rowSpan <= l.rows);
                for (int r = c.row; r < c.row + c.rowSpan; ++r)
                    for (int k = c.col; k < c.col + c.colSpan; ++k)
                        ++grid[r * l.cols + k];
                QVERIFY(c.row > prevRow || (c.row == prevRow && c.col > prevCol));
                prevRow = c.row;
                prevCol = c.col;
            }
            QCOMPARE(area, l.cols * l.rows);
            for (int n : grid)
                QCOMPARE(n, 1);
        }
    }
    void keyRoundTrip()
    {
        for (const Layout& l : allLayouts()) {
            const auto back = layoutFromKey(layoutKey(l));
            QVERIFY(back.has_value());
            QVERIFY(*back == l);
        }
    }
    void badKeysRefused()
    {
        QVERIFY(!layoutFromKey(u"2x3:0,0,2,1;0,1,1,2"));
        QVERIFY(!layoutFromKey(u"2x3:0,0,2,2;0,1,2,2"));
        QVERIFY(!layoutFromKey(u"4x1:0,0,4,1"));
        QVERIFY(!layoutFromKey(u"2x2:0,0,3,2"));
        QVERIFY(!layoutFromKey(u""));
        QVERIFY(!layoutFromKey(u"2x2: 0,0,2,2"));
        QVERIFY(!layoutFromKey(u"2x2:+0,0,2,2"));
        const auto sorted = layoutFromKey(u"2x3:0,1,1,2;0,0,2,1;1,1,1,2");
        QVERIFY(sorted.has_value());
        QCOMPARE(layoutKey(*sorted), QStringLiteral("2x3:0,0,2,1;0,1,1,2;1,1,1,2"));
    }
    void hostileKeyRefused()
    {
        QVERIFY(!layoutFromKey(u"2x2:2147483647,0,1,1"));
        QVERIFY(!layoutFromKey(u"2x2:0,0,2147483647,1"));
        QVERIFY(!layoutFromKey(u"2x2:-1,0,1,1"));
    }
    void galleryOrderIsStrict()
    {
        const auto rank = [](const Layout& l) { return l.cols == 2 && l.rows == 2 ? 0 : (l.cols == 2 ? 1 : 2); };
        const auto& all = allLayouts();
        for (qsizetype i = 1; i < all.size(); ++i) {
            const Layout &a = all[i - 1], &b = all[i];
            if (a.cells.size() != b.cells.size())
                QVERIFY(a.cells.size() < b.cells.size());
            else if (rank(a) != rank(b))
                QVERIFY(rank(a) < rank(b));
            else
                QVERIFY(layoutKey(a) < layoutKey(b));
        }
    }
    void perGridKeysUnique()
    {
        for (const auto& [cols, rows] : {std::pair{2, 2}, std::pair{2, 3}, std::pair{3, 2}}) {
            QSet<QString> keys;
            const auto list = tilings(cols, rows);
            for (const Layout& l : list)
                keys.insert(layoutKey(l));
            QCOMPARE(keys.size(), list.size());
        }
    }
    void namedShapesExist()
    {
        QSet<QString> keys;
        for (const Layout& l : allLayouts())
            keys.insert(layoutKey(l));
        QCOMPARE(layoutKey(allLayouts().first()), QStringLiteral("2x2:0,0,2,2"));
        for (const char* k : {"2x2:0,0,2,2", "2x2:0,0,1,2;1,0,1,2", "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1",
                              "3x2:0,0,1,2;1,0,1,2;2,0,1,2", "2x3:0,0,1,3;1,0,1,1;1,1,1,1;1,2,1,1"})
            QVERIFY2(keys.contains(QString::fromLatin1(k)), k);
        const auto l = layoutFromKey(u"2x3:0,0,1,3;1,0,1,3");
        QVERIFY(l.has_value());
        QCOMPARE(canonicalKey(*l), QStringLiteral("2x2:0,0,1,2;1,0,1,2"));
    }
    void rectsAreFractions()
    {
        const auto l = layoutFromKey(u"2x2:0,0,1,2;1,0,1,2");
        QVERIFY(l.has_value());
        const QVariantList r = layoutRects(*l);
        QCOMPARE(r.size(), 2);
        const QVariantMap a = r[0].toMap(), b = r[1].toMap();
        QCOMPARE(a["x"].toDouble(), 0.0);
        QCOMPARE(a["y"].toDouble(), 0.0);
        QCOMPARE(a["w"].toDouble(), 0.5);
        QCOMPARE(a["h"].toDouble(), 1.0);
        QCOMPARE(b["x"].toDouble(), 0.5);
        QCOMPARE(b["y"].toDouble(), 0.0);
        QCOMPARE(b["w"].toDouble(), 0.5);
        QCOMPARE(b["h"].toDouble(), 1.0);
    }
};
QTEST_APPLESS_MAIN(TstTilings)
#include "tst_tilings.moc"
