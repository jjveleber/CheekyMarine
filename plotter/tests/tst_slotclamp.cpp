#include "core/SlotClamp.h"
#include <QtTest>

namespace {
SlotBox corner(SlotId id, bool on, double sizeMm) { return {id, on, sizeMm, 6, 2.8, 8, 1.3}; }
SlotBox bar(SlotId id, bool on, double sizeMm) { return {id, on, sizeMm, 10, 2.8, 6, 1.3}; }
const ClampSpace kSpace{203, 123};
}

class TstSlotClamp : public QObject {
    Q_OBJECT
private slots:
    void cornerPairSharesTheRow()
    {
        const QList<SlotBox> b{corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 40)};
        QCOMPARE(maxSizeMm(SlotId::TL, b, kSpace), 26.4);
    }
    void cornerAloneUsesTheWholeArea()
    {
        const QList<SlotBox> b{corner(SlotId::TL, true, 40)};
        QCOMPARE(maxSizeMm(SlotId::TL, b, kSpace), 69.2);
    }
    void cornerColumnSharesTheHeight()
    {
        SlotBox tl = corner(SlotId::TL, true, 40), bl = corner(SlotId::BL, true, 40);
        tl.wPerMm = bl.wPerMm = 0.5;
        QCOMPARE(maxSizeMm(SlotId::TL, {tl, bl}, kSpace), 38.4);
    }
    void bannerAtMostAThirdOfThePage()
    {
        QCOMPARE(maxSizeMm(SlotId::Top, {bar(SlotId::Top, true, 10)}, kSpace), 26.9);
        QCOMPARE(maxSizeMm(SlotId::Left, {bar(SlotId::Left, true, 10)}, kSpace), 20.5);
    }
    void barsShrinkTheCornerArea()
    {
        const QList<SlotBox> b{bar(SlotId::Left, true, 20), corner(SlotId::TL, true, 10)};
        QCOMPARE(maxSizeMm(SlotId::TL, b, kSpace), 45.7);
    }
    void neverBelowTheFloor()
    {
        const ClampSpace tiny{20, 20};
        const QList<SlotBox> b{corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 40), corner(SlotId::BL, true, 40),
                               corner(SlotId::BR, true, 40), bar(SlotId::Top, true, 10), bar(SlotId::Bottom, true, 10),
                               bar(SlotId::Left, true, 10), bar(SlotId::Right, true, 10)};
        for (const SlotBox& s : b)
            QCOMPARE(maxSizeMm(s.id, b, tiny), 6.0);
    }
    void clampRounds()
    {
        QCOMPARE(clampSizeMm(33.27, 40), 33.3);
        QCOMPARE(clampSizeMm(50, 40), 40.0);
        QCOMPARE(clampSizeMm(3, 40), 6.0);
        QCOMPARE(clampSizeMm(10, 4), 6.0);
    }
    void drawnSizesAreSequential()
    {
        const QList<SlotBox> b{corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 40)};
        const QList<double> d = drawnSizesMm(b, kSpace);
        QCOMPARE(d.size(), 2);
        QCOMPARE(d[0], 26.4);
        QCOMPARE(d[1], 40.0);
        QCOMPARE(b[0].sizeMm, 40.0);
        QCOMPARE(b[1].sizeMm, 40.0);
        const QList<SlotBox> c{corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 45)};
        // TR stored 45 squeezes TL to 21.4 first, which leaves TR room for its 45.
        const QList<double> e = drawnSizesMm(c, kSpace);
        QCOMPARE(e[0], 21.4);
        QCOMPARE(e[1], 45.0);
    }
};

QTEST_APPLESS_MAIN(TstSlotClamp)
#include "tst_slotclamp.moc"
