#include "core/SlotClamp.h"
#include "core/Views.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace {
const SlotBox* find(const QList<SlotBox>& boxes, SlotId id)
{
    for (const SlotBox& b : boxes)
        if (b.id == id)
            return &b;
    return nullptr;
}

// Largest size with fixed + per * size <= limit, as an exact (unrounded) bound.
double bound(double limit, double fixed, double per)
{
    return per > 0 ? (limit - fixed) / per : std::numeric_limits<double>::infinity();
}

double floorTenth(double v)
{
    return std::floor(v * 10 + 1e-9) / 10;
}

double widthIfOn(const QList<SlotBox>& boxes, SlotId id)
{
    const SlotBox* b = find(boxes, id);
    return b && b->takesRoom ? boxWidthMm(*b, b->sizeMm) : 0;
}

double heightIfOn(const QList<SlotBox>& boxes, SlotId id)
{
    const SlotBox* b = find(boxes, id);
    return b && b->takesRoom ? boxHeightMm(*b, b->sizeMm) : 0;
}
}

double boxWidthMm(const SlotBox& box, double sizeMm) { return box.fixedWMm + box.wPerMm * sizeMm; }
double boxHeightMm(const SlotBox& box, double sizeMm) { return box.fixedHMm + box.hPerMm * sizeMm; }

double clampSizeMm(double wanted, double maxMm)
{
    const double hi = std::max(maxMm, kMinSizeMm);
    return std::min(std::max(std::round(wanted * 10) / 10, kMinSizeMm), hi);
}

double maxSizeMm(SlotId id, const QList<SlotBox>& boxes, const ClampSpace& space)
{
    const SlotBox* self = find(boxes, id);
    if (!self)
        return kMinSizeMm;
    double best = std::numeric_limits<double>::infinity();
    switch (id) {
    case SlotId::Top:
    case SlotId::Bottom:
        // At most a third of the page height, and never longer than the page is wide.
        best = std::min(bound(space.pageHMm / 3, self->fixedHMm, self->hPerMm),
                        bound(space.pageWMm, self->fixedWMm, self->wPerMm));
        break;
    case SlotId::Left:
    case SlotId::Right:
        // At most a third of the page width, and no taller than the room between the banners.
        best = std::min(bound(space.pageWMm / 3, self->fixedWMm, self->wPerMm),
                        bound(space.pageHMm - heightIfOn(boxes, SlotId::Top) - heightIfOn(boxes, SlotId::Bottom),
                              self->fixedHMm, self->hPerMm));
        break;
    default: {
        const double areaW = space.pageWMm - 2 * space.marginMm - widthIfOn(boxes, SlotId::Left) - widthIfOn(boxes, SlotId::Right);
        const double areaH = space.pageHMm - 2 * space.marginMm - heightIfOn(boxes, SlotId::Top) - heightIfOn(boxes, SlotId::Bottom);
        SlotId rowPartner, colPartner;
        switch (id) {
        case SlotId::TL: rowPartner = SlotId::TR; colPartner = SlotId::BL; break;
        case SlotId::TR: rowPartner = SlotId::TL; colPartner = SlotId::BR; break;
        case SlotId::BL: rowPartner = SlotId::BR; colPartner = SlotId::TL; break;
        default: rowPartner = SlotId::BL; colPartner = SlotId::TR; break;
        }
        const double w = widthIfOn(boxes, rowPartner), h = heightIfOn(boxes, colPartner);
        best = std::min(bound(areaW - (w > 0 ? space.gutterMm + w : 0), self->fixedWMm, self->wPerMm),
                        bound(areaH - (h > 0 ? space.gutterMm + h : 0), self->fixedHMm, self->hPerMm));
        break;
    }
    }
    // Both axes independent of size (zero per-mm coefficients): not a real field, so the floor is fine.
    if (!std::isfinite(best))
        return kMinSizeMm;
    return std::max(floorTenth(best), kMinSizeMm);
}

QList<double> drawnSizesMm(const QList<SlotBox>& boxes, const ClampSpace& space)
{
    QList<SlotBox> work = boxes;
    // The bars first: Top and Bottom alone, then Left and Right between them at their drawn heights.
    // Their drawn sizes fix the corner area.
    for (SlotId id : {SlotId::Top, SlotId::Bottom, SlotId::Left, SlotId::Right})
        for (SlotBox& b : work)
            if (b.id == id)
                b.sizeMm = clampSizeMm(b.sizeMm, maxSizeMm(id, work, space));
    const double areaW = space.pageWMm - 2 * space.marginMm - widthIfOn(work, SlotId::Left) - widthIfOn(work, SlotId::Right);
    const double areaH = space.pageHMm - 2 * space.marginMm - heightIfOn(work, SlotId::Top) - heightIfOn(work, SlotId::Bottom);
    const auto isCorner = [](SlotId id) {
        return id == SlotId::TL || id == SlotId::TR || id == SlotId::BL || id == SlotId::BR;
    };
    // Each corner scales its stored size by the smallest fit factor (at most 1) over the constraints
    // it belongs to: alone in the corner area, and with its row and column partners when both take
    // room. A pair shares one factor, so neither starves; scaling down never breaks another
    // constraint, so one pass is enough.
    const auto fit = [](double limit, double fixed, double perSize) {
        return perSize > 0 ? (limit - fixed) / perSize : std::numeric_limits<double>::infinity();
    };
    const auto pairFit = [&](const SlotBox& a, SlotId partner, bool row) {
        const SlotBox* b = find(work, partner);
        if (!a.takesRoom || !b || !b->takesRoom)
            return std::numeric_limits<double>::infinity();
        return row ? fit(areaW - space.gutterMm, a.fixedWMm + b->fixedWMm, a.wPerMm * a.sizeMm + b->wPerMm * b->sizeMm)
                   : fit(areaH - space.gutterMm, a.fixedHMm + b->fixedHMm, a.hPerMm * a.sizeMm + b->hPerMm * b->sizeMm);
    };
    QList<double> out;
    for (const SlotBox& b : work) {
        if (!isCorner(b.id)) {
            out.append(b.sizeMm);
            continue;
        }
        const SlotId rowPartner = b.id == SlotId::TL ? SlotId::TR : b.id == SlotId::TR ? SlotId::TL
                                : b.id == SlotId::BL ? SlotId::BR : SlotId::BL;
        const SlotId colPartner = b.id == SlotId::TL ? SlotId::BL : b.id == SlotId::BL ? SlotId::TL
                                : b.id == SlotId::TR ? SlotId::BR : SlotId::TR;
        const double k = std::min({1.0, fit(areaW, b.fixedWMm, b.wPerMm * b.sizeMm), fit(areaH, b.fixedHMm, b.hPerMm * b.sizeMm),
                                   pairFit(b, rowPartner, true), pairFit(b, colPartner, false)});
        out.append(clampSizeMm(floorTenth(k * b.sizeMm), b.sizeMm));
    }
    return out;
}
