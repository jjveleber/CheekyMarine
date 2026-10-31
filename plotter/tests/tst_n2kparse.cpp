#include <QJsonDocument>
#include <QtTest>

#include "core/N2kParse.h"

static QJsonObject obj(const char *s) { return QJsonDocument::fromJson(s).object(); }

static const char *kVessel =
    R"({"type":"vessel","t":1700000000.5,"pos":{"lat":47.6062,"lon":-122.3321},"sog":3.29,"cog":3.735,"hdg":3.6739,"hdgRef":"Magnetic","variation":0.2618,"depth":14.42,"depthOffset":-0.3,"stw":null,"waterTemp":287.65,"gnssTime":null,"sats":null,"rpm":null})";

class TstN2kParse : public QObject {
    Q_OBJECT
private slots:
    void hello() {
        auto h = parseHello(obj(R"({"type":"hello","schema":1,"version":"0.3.0"})"));
        QVERIFY(h.has_value());
        QCOMPARE(*h, 1);
        QVERIFY(!parseHello(obj(R"({"type":"hello","version":"0.3.0"})")).has_value());
    }
    void helloSchemaMustBeInteger() {
        QVERIFY(!parseHello(obj(R"({"type":"hello","schema":1.5,"version":"0.3.0"})")).has_value());
        QVERIFY(!parseHello(obj(R"({"type":"hello","schema":"1","version":"0.3.0"})")).has_value());
        QVERIFY(!parseHello(obj(R"({"type":"hello","schema":null,"version":"0.3.0"})")).has_value());
        auto h = parseHello(obj(R"({"type":"hello","schema":2,"version":"0.3.0"})"));
        QVERIFY(h.has_value());
        QCOMPARE(*h, 2);
    }
    void satsOutOfRangeIsNull() {
        for (double bad : {-1.0, 3e9, 1e300}) {
            QJsonObject o = obj(kVessel);
            o["sats"] = bad;
            auto v = parseVessel(o);
            QVERIFY(v.has_value());
            QVERIFY(!v->sats);
        }
    }
    void aisOutOfRangeValues() {
        const QByteArray tmpl =
            R"({"type":"ais","t":1,"targets":[{"mmsi":MMSI,"class":"A","lat":null,"lon":null,"sog":null,"cog":null,"hdg":null,"name":null,"shipType":SHIP,"navStatus":NAV,"age":1,"posAge":null}]})";
        auto parse = [&](const char *mmsi, const char *ship, const char *nav) {
            QByteArray b = tmpl;
            b.replace("MMSI", mmsi).replace("SHIP", ship).replace("NAV", nav);
            return parseAis(QJsonDocument::fromJson(b).object());
        };
        QVERIFY(parse("367123450", "37", "0").has_value());
        QVERIFY(parse("4294967295", "null", "null").has_value());
        QVERIFY(!parse("-1", "null", "null").has_value());
        QVERIFY(!parse("4294967296", "null", "null").has_value());
        QVERIFY(!parse("1e300", "null", "null").has_value());
        auto a = parse("5", "-1", "3e9");
        QVERIFY(a.has_value());
        QVERIFY(!a->first().shipType);
        QVERIFY(!a->first().navStatus);
        a = parse("5", "1e300", "2");
        QVERIFY(a.has_value());
        QVERIFY(!a->first().shipType);
        QCOMPARE(*a->first().navStatus, 2);
    }
    void vesselExample() {
        auto v = parseVessel(obj(kVessel));
        QVERIFY(v.has_value());
        QCOMPARE(v->t, 1700000000.5);
        QCOMPARE(*v->lat, 47.6062);
        QCOMPARE(*v->lon, -122.3321);
        QCOMPARE(*v->sogMs, 3.29);
        QCOMPARE(*v->cogRad, 3.735);
        QCOMPARE(*v->hdgRad, 3.6739);
        QCOMPARE(v->hdgRef, QString("Magnetic"));
        QCOMPARE(*v->variationRad, 0.2618);
        QCOMPARE(*v->depthM, 14.42);
        QCOMPARE(*v->depthOffsetM, -0.3);
        QVERIFY(!v->stwMs);
        QCOMPARE(*v->waterTempK, 287.65);
        QVERIFY(!v->gnssTime);
        QVERIFY(!v->sats);
        QVERIFY(!v->rpm);
    }
    void vesselSatsRpm() {
        QJsonObject o = obj(kVessel);
        o["sats"] = 9;
        o["rpm"] = 1800.0;
        auto v = parseVessel(o);
        QVERIFY(v.has_value());
        QCOMPARE(*v->sats, 9);
        QCOMPARE(*v->rpm, 1800.0);
    }
    void nullPos() {
        QJsonObject o = obj(kVessel);
        o["pos"] = QJsonValue::Null;
        auto v = parseVessel(o);
        QVERIFY(v.has_value());
        QVERIFY(!v->lat);
        QVERIFY(!v->lon);
    }
    // The contract is "True", "Magnetic" or null; anything else is no reference (not true).
    void hdgRefOutsideContractIsNull() {
        QJsonObject o = obj(kVessel);
        o["hdgRef"] = "Compass";
        auto v = parseVessel(o);
        QVERIFY(v.has_value());
        QVERIFY(v->hdgRef.isEmpty());
        o["hdgRef"] = "True";
        v = parseVessel(o);
        QVERIFY(v.has_value());
        QCOMPARE(v->hdgRef, QString("True"));
        o["hdgRef"] = QJsonValue::Null;
        v = parseVessel(o);
        QVERIFY(v.has_value());
        QVERIFY(v->hdgRef.isEmpty());
    }
    void unknownKeyIgnored() {
        QJsonObject o = obj(kVessel);
        o["foo"] = 1;
        QVERIFY(parseVessel(o).has_value());
    }
    void missingRequiredKey() {
        QJsonObject o = obj(kVessel);
        o.remove("depth");
        auto v = parseVessel(o);
        QVERIFY(!v.has_value());
        QVERIFY(v.error().contains("depth"));
    }
    void wrongType() {
        QJsonObject o = obj(kVessel);
        o["sog"] = "fast";
        QVERIFY(!parseVessel(o).has_value());
    }
    void aisExample() {
        auto a = parseAis(obj(
            R"({"type":"ais","t":1700000000.5,"targets":[{"mmsi":367123450,"class":"A","lat":47.7,"lon":-122.4,"sog":3.29,"cog":3.735,"hdg":3.6739,"name":null,"callsign":null,"shipType":null,"navStatus":0,"age":2.5,"posAge":2.5}]})"));
        QVERIFY(a.has_value());
        QCOMPARE(a->size(), 1);
        const AisTarget &t = a->first();
        QCOMPARE(t.mmsi, quint32(367123450));
        QCOMPARE(t.cls, QString("A"));
        QCOMPARE(*t.lat, 47.7);
        QCOMPARE(*t.sogMs, 3.29);
        QVERIFY(t.name.isEmpty());
        QVERIFY(!t.shipType);
        QCOMPARE(*t.navStatus, 0);
        QCOMPARE(t.age, 2.5);
        QCOMPARE(*t.posAge, 2.5);
    }
    void aisNullPosAndName() {
        auto a = parseAis(obj(
            R"({"type":"ais","t":1,"targets":[{"mmsi":5,"class":"B","lat":null,"lon":null,"sog":null,"cog":null,"hdg":null,"name":"SEA","callsign":null,"shipType":37,"navStatus":null,"age":1,"posAge":null}]})"));
        QVERIFY(a.has_value());
        QVERIFY(!a->first().lat);
        QVERIFY(!a->first().posAge);
        QCOMPARE(a->first().name, QString("SEA"));
        QCOMPARE(*a->first().shipType, 37);
    }
    void aisTruncatedAccepted() {
        auto a = parseAis(obj(R"({"type":"ais","t":1,"targets":[],"truncated":true,"total":900})"));
        QVERIFY(a.has_value());
        QVERIFY(a->isEmpty());
    }
    void aisMissingTargets() { QVERIFY(!parseAis(obj(R"({"type":"ais","t":1})")).has_value()); }
};

QTEST_GUILESS_MAIN(TstN2kParse)
#include "tst_n2kparse.moc"
