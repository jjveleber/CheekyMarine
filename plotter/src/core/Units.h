#pragma once

// Pixels per millimetre of a panel of w x h pixels whose diagonal is diagIn inches:
// sqrt(w^2 + h^2) / (diagIn * 25.4). The QML Units singleton sizes everything with it.
double pxPerMm(int w, int h, double diagIn);
