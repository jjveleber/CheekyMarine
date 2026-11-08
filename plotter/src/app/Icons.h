#pragma once
#include <QHash>
#include <QImage>
#include <QString>

// Runtime map images keyed by OverlayIds image id, drawn pointing up (north at rot 0): own boat 9 mm
// long (a top-down Hewescraft), AIS triangles 6 mm (class A, and the hollow variant) and 4.5 mm
// (class B), and the COG tip bar 4 mm long. Drawn in the overlayColours() of `palette`.
QHash<QString, QImage> chartIcons(double pxPerMm, const QString& palette);
