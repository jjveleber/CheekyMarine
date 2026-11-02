#pragma once
#include "core/Tilings.h"
#include <QObject>
#include <QVariantList>
#include <QVariantMap>
#include <QtQml/qqmlregistration.h>

// The cell layouts (Tilings.h) for QML: the gallery of every shape and the cell rectangles of a key.
class LayoutsQml : public QObject {
    Q_OBJECT
    QML_NAMED_ELEMENT(Layouts)
    QML_SINGLETON

public:
    using QObject::QObject;

    // [{key, cells, rects}] in allLayouts() order; rects as in rects().
    Q_INVOKABLE QVariantList gallery() const {
        QVariantList out;
        for (const Layout& l : allLayouts())
            out.append(QVariantMap{{"key", layoutKey(l)}, {"cells", int(l.cells.size())}, {"rects", layoutRects(l)}});
        return out;
    }

    // [{x, y, w, h}] as fractions of the page, in cell order; empty for a key that is not a layout.
    Q_INVOKABLE QVariantList rects(const QString& key) const {
        const auto l = layoutFromKey(key);
        return l ? layoutRects(*l) : QVariantList();
    }
};
