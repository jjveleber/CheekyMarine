#pragma once
#include "core/Units.h"
#include <QObject>
#include <QtQml/qqmlregistration.h>

// The panel pixel maths for the Units singleton (qml/Units.qml), from the pure C++ function.
class PanelMath : public QObject {
    Q_OBJECT
    QML_ELEMENT
    QML_SINGLETON

public:
    using QObject::QObject;
    Q_INVOKABLE double pxPerMm(int w, int h, double diagIn) const { return ::pxPerMm(w, h, diagIn); }
};
