#include "Geo.h"
#include <cmath>

namespace {
constexpr double kR = 6371008.8;
constexpr double kPi = 3.14159265358979323846;
double rad(double d) { return d * kPi / 180.0; }
double deg(double r) { return r * 180.0 / kPi; }
}

LatLon destination(LatLon from, double bearing, double distM)
{
    const double d = distM / kR, b = rad(bearing), p1 = rad(from.lat), l1 = rad(from.lon);
    const double p2 = std::asin(std::sin(p1) * std::cos(d) + std::cos(p1) * std::sin(d) * std::cos(b));
    const double l2 = l1 + std::atan2(std::sin(b) * std::sin(d) * std::cos(p1),
                                      std::cos(d) - std::sin(p1) * std::sin(p2));
    double lon = std::fmod(deg(l2) + 180.0, 360.0);
    if (lon < 0) lon += 360.0;
    return {deg(p2), lon - 180.0};
}

double distanceM(LatLon a, LatLon b)
{
    const double p1 = rad(a.lat), p2 = rad(b.lat);
    const double dp = p2 - p1, dl = rad(b.lon - a.lon);
    const double h = std::sin(dp / 2) * std::sin(dp / 2) + std::cos(p1) * std::cos(p2) * std::sin(dl / 2) * std::sin(dl / 2);
    return 2 * kR * std::asin(std::fmin(1.0, std::sqrt(h)));
}

double bearingDeg(LatLon from, LatLon to)
{
    const double p1 = rad(from.lat), p2 = rad(to.lat), dl = rad(to.lon - from.lon);
    const double y = std::sin(dl) * std::cos(p2);
    const double x = std::cos(p1) * std::sin(p2) - std::sin(p1) * std::cos(p2) * std::cos(dl);
    double b = std::fmod(deg(std::atan2(y, x)), 360.0);
    if (b < 0) b += 360.0;
    return b;
}

double metresPerPixel(double latDeg, double zoom)
{
    return 40075016.686 * std::cos(rad(latDeg)) / (512.0 * std::pow(2.0, zoom));
}

QList<LatLon> syntheticTrack(int n, double stepM) {
    const LatLon way[] = {{47.9482896, -122.3136073}, {47.9021326, -122.3743223}, {47.9080896, -122.4492273}};
    QList<LatLon> route;
    LatLon cur = way[0];
    for (int leg = 1; leg < 3; ++leg) {
        while (distanceM(cur, way[leg]) > stepM) {
            route << cur;
            cur = destination(cur, bearingDeg(cur, way[leg]), stepM);
        }
    }
    route << cur;
    QList<LatLon> out;
    if (route.size() < 2) {
        for (int i = 0; i < n; ++i) out << route[0];
        return out;
    }
    const int period = 2 * (route.size() - 1);
    for (int i = 0; i < n; ++i) {
        const int k = i % period;
        out << route[k < route.size() ? k : period - k];
    }
    return out;
}
