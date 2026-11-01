#pragma once
#include "Slots.h"
#include <QList>

// A slot's box is fixed + per * sizeMm in each axis (the QML page measures fixed and per from its
// layout and the field's widestSample). takesRoom: the slot is on, or any slot is in edit mode.
struct SlotBox {
    SlotId id;
    bool takesRoom;
    double sizeMm;
    double fixedWMm, wPerMm, fixedHMm, hPerMm;
};

// The page width without the tab bar strip and the height above the notice line, at the bar-shown width.
struct ClampSpace {
    double pageWMm, pageHMm;
    double marginMm = 1.5;
    double gutterMm = 2;
};

double boxWidthMm(const SlotBox& box, double sizeMm);
double boxHeightMm(const SlotBox& box, double sizeMm);
// Rounded to 0.1, at least kMinSizeMm, at most max(maxMm, kMinSizeMm).
double clampSizeMm(double wanted, double maxMm);
// The largest 0.1 mm step at which `id`'s box fits, the other boxes at their given sizeMm (a Top or
// Bottom bar also no longer than the page width, a Left or Right bar no taller than its height).
// Never below kMinSizeMm.
double maxSizeMm(SlotId id, const QList<SlotBox>& boxes, const ClampSpace& space);
// The size to draw each slot at, in the boxes' order. The bars first, each clamped alone (maxSizeMm);
// then each corner at its stored size times the smallest fit factor k <= 1 over its constraints: alone
// in the corner area, and its row and column pairs (both taking room) sharing the area width and
// height. Floored to 0.1 mm and to kMinSizeMm. The stored sizes in `boxes` are not changed.
QList<double> drawnSizesMm(const QList<SlotBox>& boxes, const ClampSpace& space);
