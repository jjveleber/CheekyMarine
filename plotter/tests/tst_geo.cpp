#include "core/Geo.h"
#include <QtTest>
#include <cmath>

class TstGeo : public QObject {
    Q_OBJECT
private slots:
    void distanceMatchesHaversine()
    {
        const long double pi = 3.141592653589793238462643L, R = 6371008.8L;
        const long double p1 = 47.98L * pi / 180, p2 = 48.11L * pi / 180;
        const long double dp = p2 - p1, dl = (-122.75L + 122.23L) * pi / 180;
        const long double h = sinl(dp / 2) * sinl(dp / 2) + cosl(p1) * cosl(p2) * sinl(dl / 2) * sinl(dl / 2);
        const long double ref = 2 * R * asinl(sqrtl(h));
        QVERIFY(std::fabs(distanceM({47.98, -122.23}, {48.11, -122.75}) - static_cast<double>(ref)) < 1.0);
    }
    void destinationRoundTrip()
    {
        const LatLon a{37.0, -122.0};
        const LatLon b = destination(a, 70.0, 1000.0);
        QVERIFY(std::fabs(distanceM(a, b) - 1000.0) < 0.01);
        QVERIFY(std::fabs(bearingDeg(a, b) - 70.0) < 0.001);
    }
    void bearingNormalised()
    {
        QVERIFY(std::fabs(bearingDeg({0, 0}, {0, -1}) - 270.0) < 1e-9);
    }
    void metresPerPixelEquatorZoom0()
    {
        QVERIFY(std::fabs(metresPerPixel(0, 0) - 78271.517) < 0.001);
        QVERIFY(std::fabs(metresPerPixel(60, 0) - 78271.517 / 2) < 0.001);
    }
};
QTEST_APPLESS_MAIN(TstGeo)
#include "tst_geo.moc"
