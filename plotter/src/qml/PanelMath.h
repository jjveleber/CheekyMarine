#pragma once
#include "core/SlotClamp.h"
#include "core/Units.h"
#include "core/Views.h"
#include <QDebug>
#include <QObject>
#include <QVariantList>
#include <QVariantMap>
#include <QtQml/qqmlregistration.h>

// The panel pixel maths for the Units singleton (qml/Units.qml), and the slot size clamp and tab bar
// capacity for the pages, from the pure C++ functions.
class PanelMath : public QObject {
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

public:
    using QObject::QObject;
    Q_INVOKABLE double pxPerMm(int w, int h, double diagIn) const { return ::pxPerMm(w, h, diagIn); }
    Q_INVOKABLE int favouriteCapacity(double barHeightMm) const { return ::favouriteCapacity(barHeightMm); }

    // boxes: [{id, takesRoom, sizeMm, fixedWMm, wPerMm, fixedHMm, hPerMm}]; space: {pageWMm, pageHMm}.
    // A box with an unknown id is logged and left out.
    Q_INVOKABLE double maxSlotSizeMm(const QString& slotId, const QVariantList& boxes, const QVariantMap& space) const {
        const auto id = slotIdFromName(slotId);
        if (!id) {
            qWarning() << "PanelMath: unknown slot" << slotId;
            return kMinSizeMm;
        }
        return maxSizeMm(*id, toBoxes(boxes), toSpace(space));
    }

    // The drawn size of each box, in the boxes' order (a box with an unknown id keeps its sizeMm).
    Q_INVOKABLE QVariantList drawnSizesMm(const QVariantList& boxes, const QVariantMap& space) const {
        QList<int> at; // index into `boxes` of each known box
        const QList<SlotBox> known = toBoxes(boxes, &at);
        const QList<double> drawn = ::drawnSizesMm(known, toSpace(space));
        QVariantList out;
        for (const QVariant& b : boxes) out.append(b.toMap().value("sizeMm").toDouble());
        for (int i = 0; i < drawn.size(); ++i) out[at[i]] = drawn[i];
        return out;
    }

private:
    static QList<SlotBox> toBoxes(const QVariantList& boxes, QList<int>* at = nullptr) {
        QList<SlotBox> out;
        for (int i = 0; i < boxes.size(); ++i) {
            const QVariantMap m = boxes[i].toMap();
            const auto id = slotIdFromName(m.value("id").toString());
            if (!id) {
                qWarning() << "PanelMath: unknown slot" << m.value("id");
                continue;
            }
            out.append({*id, m.value("takesRoom").toBool(), m.value("sizeMm").toDouble(), m.value("fixedWMm").toDouble(),
                        m.value("wPerMm").toDouble(), m.value("fixedHMm").toDouble(), m.value("hPerMm").toDouble()});
            if (at) at->append(i);
        }
        return out;
    }
    static ClampSpace toSpace(const QVariantMap& space) {
        return {space.value("pageWMm").toDouble(), space.value("pageHMm").toDouble()};
    }
};
