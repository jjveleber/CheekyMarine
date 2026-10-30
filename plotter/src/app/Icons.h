#pragma once
#include <QHash>
#include <QImage>
#include <QString>

// Runtime map images keyed by OverlayIds image id, drawn pointing up (north at rot 0): own boat 12 mm
// long, AIS triangles 8 mm (class A, and the hollow variant) and 6 mm (class B). Drawn
// in the overlayColours() of `palette`.
QHash<QString, QImage> chartIcons(double pxPerMm, const QString& palette);
