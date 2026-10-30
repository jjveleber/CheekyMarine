#include "core/Overlays.h"
#include <QJsonArray>
#include <QtTest>
#include <cmath>

namespace {
constexpr double kPi = 3.14159265358979323846;
QList<QJsonObject> byKind(const QJsonObject& fc, const QString& kind)
{
    QList<QJsonObject> out;
    for (const auto& f : fc["features"].toArray()) {
        const QJsonObject o = f.toObject();
        if (o["properties"].toObject()["kind"].toString() == kind) out << o;
    }
    return out;
}
LatLon at(const QJsonObject& f, int i)
{
    const QJsonArray c = f["geometry"].toObject()["coordinates"].toArray();
    const QJsonArray p = c[i].toArray();
    return {p[1].toDouble(), p[0].toDouble()};
}
VesselState base()
{
    VesselState v;
    v.lat = 48.0;
    v.lon = -122.5;
    return v;
}
double rotOf(const QJsonObject& f) { return f["properties"].toObject()["rot"].toDouble(); }
}

class TstOverlays : public QObject {
    Q_OBJECT
private slots:
    void magneticHeadingAddsVariation()
    {
        VesselState v = base();
        v.hdgRad = 1.0;
        v.variationRad = 0.2731;
        v.hdgRef = "Magnetic";
        const auto boat = byKind(ownShipGeoJson(v), "boat");
        QCOMPARE(boat.size(), 1);
        QVERIFY(std::fabs(rotOf(boat[0]) - (1.0 + 0.2731) * 180 / kPi) < 1e-6);
    }
    void trueHeadingNotAdjusted()
    {
        VesselState v = base();
        v.hdgRad = 1.0;
        v.variationRad = 0.2731;
        v.hdgRef = "True";
        QVERIFY(std::fabs(rotOf(byKind(ownShipGeoJson(v), "boat")[0]) - 180 / kPi) < 1e-6);
    }
    void rotWraps()
    {
        VesselState v = base();
        v.hdgRad = -0.5;
        v.hdgRef = "True";
        QVERIFY(std::fabs(rotOf(byKind(ownShipGeoJson(v), "boat")[0]) - (360 - 0.5 * 180 / kPi)) < 1e-6);
        v.hdgRad = 6.0;
        v.variationRad = 0.5;
        v.hdgRef = "Magnetic";
        const double r = rotOf(byKind(ownShipGeoJson(v), "boat")[0]);
        QVERIFY(r >= 0 && r < 360);
        QVERIFY(std::fabs(r - (6.5 - 2 * kPi) * 180 / kPi) < 1e-6);
    }
    void rotFallsBackToCogThenZero()
    {
        VesselState v = base();
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0);
        v.cogRad = kPi / 2;
        v.sogMs = 3.0;
        QVERIFY(std::fabs(rotOf(byKind(ownShipGeoJson(v), "boat")[0]) - 90.0) < 1e-9);
    }
    // Without heading the boat turns to COG only above 0.5 kn, like the COG vector and the head-up
    // camera; slower, COG is noise and the icon points north (the camera's bearing then).
    void rotIgnoresCogWhenSlow()
    {
        VesselState v = base();
        v.cogRad = kPi / 2;
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0); // no SOG
        v.sogMs = 0.1;
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0);
        v.sogMs = 0.2572;
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0);
        v.sogMs = 0.26;
        QVERIFY(std::fabs(rotOf(byKind(ownShipGeoJson(v), "boat")[0]) - 90.0) < 1e-9);
    }
    // Spec 6.6: a magnetic heading is true only with variation. Without it there is no true
    // heading: no heading line, and the boat turns to COG (gated) like the camera.
    void magneticWithoutVariationIsNoHeading()
    {
        VesselState v = base();
        v.hdgRad = 1.0;
        v.hdgRef = "Magnetic";
        QCOMPARE(byKind(ownShipGeoJson(v), "heading").size(), 0);
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0);
        v.cogRad = kPi / 2;
        v.sogMs = 3.0;
        QCOMPARE(byKind(ownShipGeoJson(v), "heading").size(), 0);
        QVERIFY(std::fabs(rotOf(byKind(ownShipGeoJson(v), "boat")[0]) - 90.0) < 1e-9);
    }
    // A heading with no reference (null hdgRef) is not known to be true either.
    void headingWithoutReferenceIsNoHeading()
    {
        VesselState v = base();
        v.hdgRad = 1.0;
        v.variationRad = 0.2731;
        QCOMPARE(byKind(ownShipGeoJson(v), "heading").size(), 0);
        QCOMPARE(rotOf(byKind(ownShipGeoJson(v), "boat")[0]), 0.0);
    }
    void headingLine50km()
    {
        VesselState v = base();
        v.hdgRad = kPi / 2;
        v.hdgRef = "True";
        const auto h = byKind(ownShipGeoJson(v), "heading");
        QCOMPARE(h.size(), 1);
        QCOMPARE(h[0]["geometry"].toObject()["coordinates"].toArray().size(), 2);
        QVERIFY(std::fabs(at(h[0], 0).lat - 48.0) < 1e-12 && std::fabs(at(h[0], 0).lon + 122.5) < 1e-12);
        QVERIFY(std::fabs(distanceM(at(h[0], 0), at(h[0], 1)) - 50000.0) < 0.1);
    }
    void cogVectorLength()
    {
        VesselState v = base();
        v.cogRad = 1.0;
        v.sogMs = 5.0;
        const auto c = byKind(ownShipGeoJson(v), "cog");
        QCOMPARE(c.size(), 1);
        QVERIFY(std::fabs(distanceM(at(c[0], 0), at(c[0], 1)) - 600.0) < 0.1);
        QVERIFY(std::fabs(bearingDeg(at(c[0], 0), at(c[0], 1)) - 1.0 * 180 / kPi) < 0.01);
    }
    void slowSogNoCog()
    {
        VesselState v = base();
        v.cogRad = 1.0;
        v.sogMs = 0.1;
        QCOMPARE(byKind(ownShipGeoJson(v), "cog").size(), 0);
    }
    void noPositionNoFeatures()
    {
        VesselState v;
        v.hdgRad = 1.0;
        v.cogRad = 1.0;
        v.sogMs = 5.0;
        QCOMPARE(ownShipGeoJson(v)["features"].toArray().size(), 0);
    }
    void tracksDropShort()
    {
        QList<QList<LatLon>> t{{{1, 2}}, {{1, 2}, {3, 4}}, {}};
        const QJsonArray fs = tracksGeoJson(t)["features"].toArray();
        QCOMPARE(fs.size(), 1);
        const QJsonArray c = fs[0].toObject()["geometry"].toObject()["coordinates"].toArray();
        QCOMPARE(c[0].toArray()[0].toDouble(), 2.0); // [lon, lat]
        QCOMPARE(c[0].toArray()[1].toDouble(), 1.0);
    }
    void aisHollowAndVector()
    {
        AisTarget t;
        t.mmsi = 366123456;
        t.cls = "A";
        t.lat = 48.1;
        t.lon = -122.6;
        t.cogRad = 0.5;
        t.sogMs = 4.0;
        QList<AisTarget> l;
        t.posAge = 61;
        l << t;
        t.posAge = 59;
        l << t;
        t.posAge.reset();
        l << t;
        const QJsonObject fc = aisGeoJson(l, VesselState{});
        const auto pts = byKind(fc, "ais");
        QCOMPARE(pts.size(), 3);
        QCOMPARE(pts[0]["properties"].toObject()["hollow"].toBool(), true);
        QCOMPARE(pts[1]["properties"].toObject()["hollow"].toBool(), false);
        QCOMPARE(pts[2]["properties"].toObject()["hollow"].toBool(), false);
        QCOMPARE(pts[0]["properties"].toObject()["cls"].toString(), QString("A"));
        QCOMPARE(pts[0]["properties"].toObject()["mmsi"].toDouble(), 366123456.0);
        QVERIFY(std::fabs(rotOf(pts[0]) - 0.5 * 180 / kPi) < 1e-9);
        const auto vecs = byKind(fc, "aisvec");
        QCOMPARE(vecs.size(), 3);
        QVERIFY(std::fabs(distanceM(at(vecs[0], 0), at(vecs[0], 1)) - 1440.0) < 0.1);
    }
    void aisNoPositionOrNoVector()
    {
        AisTarget a;
        a.mmsi = 1;
        a.cogRad = 1.0;
        a.sogMs = 3.0;
        AisTarget b;
        b.mmsi = 2;
        b.lat = 1.0;
        b.lon = 2.0;
        const QJsonObject fc = aisGeoJson({a, b}, VesselState{});
        QCOMPARE(fc["features"].toArray().size(), 1);
        QCOMPARE(byKind(fc, "ais").size(), 1);
    }
};
QTEST_APPLESS_MAIN(TstOverlays)
#include "tst_overlays.moc"
