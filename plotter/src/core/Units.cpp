#include "Units.h"
#include <cmath>

double pxPerMm(int w, int h, double diagIn) {
    return std::hypot(double(w), double(h)) / (diagIn * 25.4);
}
