#include "core/Fields.h"
#include <QtTest>
#include <ctime>

class TstFields : public QObject {
    Q_OBJECT
    static QString fv(Field f, const VesselState& s, const UnitPrefs& p = {}) { return formatValue(f, s, p); }
    static VesselState depth(double m, std::optional<double> off = std::nullopt) {
        VesselState s;
        s.depthM = m;
        s.depthOffsetM = off;
        return s;
    }
private slots:
    void initTestCase() {
        qputenv("TZ", "UTC");
        tzset();
    }

    void depthFeetOffset() {
        UnitPrefs p;
        auto s = depth(14.42, -0.3);
        QCOMPARE(fv(Field::Depth, s, p), QStringLiteral("46"));
        p.applyDepthOffset = false;
        QCOMPARE(fv(Field::Depth, s, p), QStringLiteral("47"));
    }
    void depthSmallFeet() {
        UnitPrefs p;
        p.applyDepthOffset = false;
        QCOMPARE(fv(Field::Depth, depth(2.5), p), QStringLiteral("8.2"));
    }
    void depthRoundThenWhole() {
        UnitPrefs p;
        p.depth = DepthUnit::Metres;
        QCOMPARE(fv(Field::Depth, depth(9.96), p), QStringLiteral("10"));
        QCOMPARE(fv(Field::Depth, depth(9.94), p), QStringLiteral("9.9"));
        p.depth = DepthUnit::Fathoms;
        QCOMPARE(fv(Field::Depth, depth(18.288), p), QStringLiteral("10"));
    }
    void depthNegativeOffset() {
        UnitPrefs p;
        p.depth = DepthUnit::Metres;
        QCOMPARE(fv(Field::Depth, depth(0.0, -0.01), p), QStringLiteral("0.0"));  // no negative zero
        QCOMPARE(fv(Field::Depth, depth(0.0, -0.1), p), QStringLiteral("-0.1"));  // honest negative stays
    }
    void depthMissingAndLabels() {
        QCOMPARE(fv(Field::Depth, VesselState{}), QStringLiteral("--"));
        UnitPrefs p;
        QCOMPARE(unitLabel(Field::Depth, VesselState{}, p), QStringLiteral("ft"));
        p.depth = DepthUnit::Metres;
        QCOMPARE(unitLabel(Field::Depth, VesselState{}, p), QStringLiteral("m"));
        p.depth = DepthUnit::Fathoms;
        QCOMPARE(unitLabel(Field::Depth, VesselState{}, p), QStringLiteral("fm"));
    }
    void speed() {
        VesselState s;
        s.sogMs = 3.29;
        s.stwMs = 3.29;
        UnitPrefs p;
        QCOMPARE(fv(Field::Sog, s, p), QStringLiteral("6.4"));
        QCOMPARE(fv(Field::Stw, s, p), QStringLiteral("6.4"));
        QCOMPARE(unitLabel(Field::Sog, s, p), QStringLiteral("kn"));
        p.speed = SpeedUnit::Mph;
        QCOMPARE(fv(Field::Sog, s, p), QStringLiteral("7.4"));
        QCOMPARE(unitLabel(Field::Stw, s, p), QStringLiteral("mph"));
        p.speed = SpeedUnit::Kmh;
        QCOMPARE(fv(Field::Sog, s, p), QStringLiteral("11.8"));
        QCOMPARE(unitLabel(Field::Sog, s, p), QStringLiteral("km/h"));
        QCOMPARE(fv(Field::Sog, VesselState{}), QStringLiteral("--"));
        QCOMPARE(fv(Field::Stw, VesselState{}), QStringLiteral("--"));
    }
    void courses() {
        VesselState s;
        s.cogRad = 0.1222;
        s.hdgRad = 3.14159265358979;
        QCOMPARE(fv(Field::Cog, s), QStringLiteral("007"));
        QCOMPARE(fv(Field::Heading, s), QStringLiteral("180"));
        QCOMPARE(unitLabel(Field::Cog, s, {}), QStringLiteral("°T"));
        s.hdgRef = QStringLiteral("Magnetic");
        QCOMPARE(unitLabel(Field::Heading, s, {}), QStringLiteral("°M"));
        s.hdgRef = QStringLiteral("True");
        QCOMPARE(unitLabel(Field::Heading, s, {}), QStringLiteral("°T"));
        QCOMPARE(fv(Field::Cog, VesselState{}), QStringLiteral("--"));
        QCOMPARE(fv(Field::Heading, VesselState{}), QStringLiteral("--"));
        QCOMPARE(unitLabel(Field::Heading, VesselState{}, {}), QString::fromUtf8("\xC2\xB0"));  // no reference: bare degree sign
        s.cogRad = 6.2831;  // 359.998 degrees rounds to 360, which wraps to 000
        QCOMPARE(fv(Field::Cog, s), QStringLiteral("000"));
    }
    void waterTemp() {
        VesselState s;
        s.waterTempK = 287.65;
        UnitPrefs p;
        QCOMPARE(fv(Field::WaterTemp, s, p), QStringLiteral("58.1"));
        QCOMPARE(unitLabel(Field::WaterTemp, s, p), QStringLiteral("°F"));
        p.temp = TempUnit::C;
        QCOMPARE(fv(Field::WaterTemp, s, p), QStringLiteral("14.5"));
        QCOMPARE(unitLabel(Field::WaterTemp, s, p), QStringLiteral("°C"));
        QCOMPARE(fv(Field::WaterTemp, VesselState{}, p), QStringLiteral("--"));
    }
    void position() {
        VesselState s;
        s.lat = 47.98;
        s.lon = -122.23;
        QCOMPARE(fv(Field::Position, s), QString::fromUtf8("47\xC2\xB0" "58.800'N\n122\xC2\xB0" "13.800'W"));
        QCOMPARE(unitLabel(Field::Position, s, {}), QString());
        s.lat = -33.5;
        s.lon = 151.25;
        QCOMPARE(fv(Field::Position, s), QString::fromUtf8("33\xC2\xB0" "30.000'S\n151\xC2\xB0" "15.000'E"));
        s.lat = 47.99999999;  // rounds up to 60.000 minutes: carries into the degrees
        s.lon = 0.0;
        QCOMPARE(fv(Field::Position, s), QString::fromUtf8("48\xC2\xB0" "00.000'N\n000\xC2\xB0" "00.000'E"));
        VesselState half;
        half.lat = 47.98;
        QCOMPARE(fv(Field::Position, half), QStringLiteral("--"));
        QCOMPARE(fv(Field::Position, VesselState{}), QStringLiteral("--"));
    }
    void timeField() {
        VesselState s;
        s.gnssTime = 3661.0;  // 01:01:01 UTC on 1970-01-01
        s.t = 7200.0;
        QCOMPARE(fv(Field::Time, s), QStringLiteral("01:01:01"));
        s.gnssTime.reset();  // fallback to t
        QCOMPARE(fv(Field::Time, s), QStringLiteral("02:00:00"));
        QCOMPARE(fv(Field::Time, VesselState{}), QStringLiteral("--"));
        QCOMPARE(unitLabel(Field::Time, s, {}), QString());
    }
    void rpm() {
        VesselState s;
        s.rpm = 2349.6;
        QCOMPARE(fv(Field::Rpm, s), QStringLiteral("2350"));
        QCOMPARE(unitLabel(Field::Rpm, s, {}), QStringLiteral("rpm"));
        QCOMPARE(fv(Field::Rpm, VesselState{}), QStringLiteral("--"));
    }
    void names() {
        const Field all[] = {Field::Depth, Field::Sog, Field::Stw, Field::Cog, Field::Heading,
                             Field::WaterTemp, Field::Position, Field::Time, Field::Rpm};
        const char* expect[] = {"depth", "sog", "stw", "cog", "hdg", "wtemp", "pos", "time", "rpm"};
        for (int i = 0; i < 9; ++i) {
            QCOMPARE(fieldName(all[i]), QString::fromLatin1(expect[i]));
            auto r = fieldFromName(fieldName(all[i]));
            QVERIFY(r.has_value());
            QCOMPARE(int(*r), int(all[i]));
        }
        QVERIFY(!fieldFromName(u"bogus").has_value());
    }
};

QTEST_APPLESS_MAIN(TstFields)
#include "tst_fields.moc"
