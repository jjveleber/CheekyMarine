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
        best = bound(space.pageHMm / 3, self->fixedHMm, self->hPerMm);
        break;
    case SlotId::Left:
    case SlotId::Right:
        best = bound(space.pageWMm / 3, self->fixedWMm, self->wPerMm);
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
    static const SlotId order[] = {SlotId::Top, SlotId::Bottom, SlotId::Left, SlotId::Right,
                                   SlotId::TL,  SlotId::TR,     SlotId::BL,   SlotId::BR};
    QList<SlotBox> work = boxes;
    for (SlotId id : order)
        for (SlotBox& b : work)
            if (b.id == id)
                b.sizeMm = clampSizeMm(b.sizeMm, maxSizeMm(id, work, space));
    QList<double> out;
    for (const SlotBox& b : work)
        out.append(b.sizeMm);
    return out;
}
