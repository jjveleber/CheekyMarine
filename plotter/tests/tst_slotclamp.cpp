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
    void partnersMirrorForEveryCorner()
    {
        const struct { SlotId id, row, col; } cases[] = {{SlotId::TR, SlotId::TL, SlotId::BR},
                                                        {SlotId::BL, SlotId::BR, SlotId::TL},
                                                        {SlotId::BR, SlotId::BL, SlotId::TR}};
        for (const auto& c : cases) {
            QCOMPARE(maxSizeMm(c.id, {corner(c.id, true, 40), corner(c.row, true, 40)}, kSpace), 26.4);
            SlotBox a = corner(c.id, true, 40), b = corner(c.col, true, 40);
            a.wPerMm = b.wPerMm = 0.5;
            QCOMPARE(maxSizeMm(c.id, {a, b}, kSpace), 38.4);
        }
    }
    void partnerNotTakingRoomIsIgnored()
    {
        const QList<SlotBox> b{corner(SlotId::TL, true, 40), corner(SlotId::TR, false, 40)};
        QCOMPARE(maxSizeMm(SlotId::TL, b, kSpace), 69.2);
    }
    void unknownIdIsFloor()
    {
        // An id with no box in the list (an out-of-range SlotId cast hits the same path).
        QCOMPARE(maxSizeMm(SlotId::TR, {corner(SlotId::TL, true, 40)}, kSpace), 6.0);
        QCOMPARE(maxSizeMm(static_cast<SlotId>(99), {corner(SlotId::TL, true, 40)}, kSpace), 6.0);
    }
    void bannerShrinksCornerHeight()
    {
        SlotBox tl = corner(SlotId::TL, true, 40);
        tl.wPerMm = 0.5;
        QCOMPARE(maxSizeMm(SlotId::TL, {bar(SlotId::Top, true, 20), tl}, kSpace), 61.5);
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
    // A Top or Bottom bar's length fits the page width (width binds before the third-of-height rule).
    void bannerWidthFitsThePage()
    {
        SlotBox top = bar(SlotId::Top, true, 30);
        top.wPerMm = 8;
        QCOMPARE(maxSizeMm(SlotId::Top, {top}, kSpace), 24.1);
        QCOMPARE(drawnSizesMm({top}, kSpace), (QList<double>{24.1}));
    }
    // A Left or Right bar's height fits the page height.
    void barHeightFitsThePage()
    {
        SlotBox left = bar(SlotId::Left, true, 30);
        left.hPerMm = 8;
        QCOMPARE(maxSizeMm(SlotId::Left, {left}, kSpace), 14.6);
        QCOMPARE(drawnSizesMm({left}, kSpace), (QList<double>{14.6}));
    }
    // Corners in a row (or column) scale by one shared factor instead of the first one starving.
    void drawnSizesShareTheRoom()
    {
        // k = (200 - 2 - 6 - 6) / (2.8 * 40 + 2.8 * 40) = 0.8304.
        const QList<SlotBox> b{corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 40)};
        QCOMPARE(drawnSizesMm(b, kSpace), (QList<double>{33.2, 33.2}));
        QCOMPARE(b[0].sizeMm, 40.0);
        QCOMPARE(b[1].sizeMm, 40.0);
        // k = 186 / (2.8 * 60) = 1.107, capped at 1: they fit as stored.
        QCOMPARE(drawnSizesMm({corner(SlotId::TL, true, 40), corner(SlotId::TR, true, 20)}, kSpace), (QList<double>{40.0, 20.0}));
        // k = 186 / (2.8 * 180) = 0.369.
        QCOMPARE(drawnSizesMm({corner(SlotId::TL, true, 90), corner(SlotId::TR, true, 90)}, kSpace), (QList<double>{33.2, 33.2}));
        // A partner that takes no room is ignored: TL alone fits at 40.
        QCOMPARE(drawnSizesMm({corner(SlotId::TL, true, 40), corner(SlotId::TR, false, 40)}, kSpace).at(0), 40.0);
    }
};

QTEST_APPLESS_MAIN(TstSlotClamp)
#include "tst_slotclamp.moc"
