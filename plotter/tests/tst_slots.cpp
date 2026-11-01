#include "core/Settings.h"
#include "core/Slots.h"
#include "core/Store.h"
#include "core/Units.h"
#include "core/VesselModel.h"
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QtTest>

namespace {
QJsonArray parse(const char* json) { return QJsonDocument::fromJson(json).array(); }

// A Store, Settings and VesselModel in a temporary directory.
struct Env {
    QTemporaryDir dir;
    std::unique_ptr<Store> store;
    std::unique_ptr<Settings> settings;
    VesselModel vessel;
    Env() {
        auto s = Store::open(dir.path());
        if (s) store = std::move(*s);
        if (store) settings = std::make_unique<Settings>(*store);
    }
};
} // namespace

class TstSlots : public QObject {
    Q_OBJECT
private slots:
    void defaults() {
        const QList<SlotConfig> want{
            {SlotId::TL, true, Field::Depth, SlotSize::Large},
            {SlotId::TR, true, Field::Sog, SlotSize::Large},
            {SlotId::BL, false, Field::Cog, SlotSize::Medium},
            {SlotId::BR, false, Field::WaterTemp, SlotSize::Medium},
            {SlotId::Top, false, Field::Time, SlotSize::Small},
            {SlotId::Bottom, false, Field::Position, SlotSize::Small},
            {SlotId::Left, false, Field::Stw, SlotSize::Medium},
            {SlotId::Right, false, Field::Heading, SlotSize::Medium},
        };
        QCOMPARE(defaultSlots(), want);
    }

    void jsonRoundTrip() {
        QList<SlotConfig> s = defaultSlots();
        s[2] = {SlotId::BL, true, Field::Rpm, SlotSize::Large};
        s[5] = {SlotId::Bottom, true, Field::Position, SlotSize::Medium};
        s[0].on = false;
        const QJsonArray j = slotsToJson(s);
        QCOMPARE(j.size(), 8);
        QCOMPARE(j.at(2).toObject(), parse(R"([{"id":"BL","on":true,"field":"rpm","size":"large"}])").at(0).toObject());
        QCOMPARE(slotsFromJson(j), s);
        QCOMPARE(slotsFromJson(slotsToJson(defaultSlots())), defaultSlots());
    }

    void unknownFieldTakesTheSlotDefault() {
        const QList<SlotConfig> got = slotsFromJson(parse(R"([{"id":"TL","on":true,"field":"warp","size":"large"}])"));
        QCOMPARE(got.size(), 8);
        QCOMPARE(got.at(0), (SlotConfig{SlotId::TL, true, Field::Depth, SlotSize::Large}));
        QCOMPARE(got.mid(1), defaultSlots().mid(1));
    }

    void missingAndUnknownEntries() {
        QCOMPARE(slotsFromJson(QJsonArray()), defaultSlots());
        // Unknown id, non-object entries: ignored. A partial entry keeps what it has.
        const QList<SlotConfig> got = slotsFromJson(parse(
            R"([{"id":"XX","on":true}, 5, "TL", {"id":"BL","on":true}, {"id":"BL","on":false},
                {"id":"Right","on":"yes","field":"rpm","size":"huge"}])"));
        QList<SlotConfig> want = defaultSlots();
        want[2].on = true;            // first BL wins
        want[7].field = Field::Rpm;   // on and size unknown: defaults
        QCOMPARE(got, want);
    }

    void pxPerMmOfThePanels() {
        QVERIFY(std::abs(pxPerMm(1024, 600, 10.1) - 4.626) <= 0.001);
        QVERIFY(std::abs(pxPerMm(1280, 800, 10.1) - 5.884) <= 0.001);
        QVERIFY(std::abs(pxPerMm(1280, 800, 7.0) - 8.490) <= 0.001);
    }

    void fieldLabelsAndChoices() {
        QCOMPARE(fieldLabel(Field::Depth), QStringLiteral("Depth"));
        QCOMPARE(fieldLabel(Field::WaterTemp), QStringLiteral("Water temp"));
        const QVariantList c = fieldChoices();
        QCOMPARE(c.size(), 9);
        QCOMPARE(c.at(1).toMap().value("name").toString(), QStringLiteral("sog"));
        QCOMPARE(c.at(1).toMap().value("label").toString(), QStringLiteral("SOG"));
    }

    // The formatted and unit texts the slot and cell models show follow the vessel and the unit settings.
    void fieldRoleTextFollowsVesselAndUnits() {
        Env e;
        QVERIFY(e.settings);
        QCOMPARE(fieldRoleText(Field::Depth, false, e.vessel, *e.settings), QStringLiteral("--"));
        QCOMPARE(fieldRoleText(Field::Depth, true, e.vessel, *e.settings), QStringLiteral("ft"));
        VesselState s;
        s.depthM = 12 * 0.3048;
        s.sogMs = 5.2 * 1852.0 / 3600.0;
        e.vessel.setLive(true);
        e.vessel.setState(s);
        QCOMPARE(fieldRoleText(Field::Depth, false, e.vessel, *e.settings), QStringLiteral("12"));
        QCOMPARE(fieldRoleText(Field::Sog, false, e.vessel, *e.settings), QStringLiteral("5.2"));
        QCOMPARE(fieldRoleText(Field::Sog, true, e.vessel, *e.settings), QStringLiteral("kn"));
        e.settings->setDepthUnit("m");
        QCOMPARE(fieldRoleText(Field::Depth, false, e.vessel, *e.settings), QStringLiteral("3.7"));
        QCOMPARE(fieldRoleText(Field::Depth, true, e.vessel, *e.settings), QStringLiteral("m"));
        e.settings->setSpeedUnit("kmh");
        QCOMPARE(fieldRoleText(Field::Sog, true, e.vessel, *e.settings), QStringLiteral("km/h"));
    }

    // Each unit setting calls the refresh once.
    void unitSettingsCallRefresh_data() {
        QTest::addColumn<QString>("setting");
        for (const char* s : {"depthUnit", "speedUnit", "tempUnit", "applyDepthOffset"}) QTest::newRow(s) << QString(s);
    }
    void unitSettingsCallRefresh() {
        QFETCH(QString, setting);
        Env e;
        QVERIFY(e.settings);
        QObject context;
        int calls = 0;
        onUnitSettingsChanged(*e.settings, &context, [&calls] { ++calls; });
        if (setting == "depthUnit") e.settings->setDepthUnit("m");
        if (setting == "speedUnit") e.settings->setSpeedUnit("kmh");
        if (setting == "tempUnit") e.settings->setTempUnit("C");
        if (setting == "applyDepthOffset") e.settings->setApplyDepthOffset(false);
        QCOMPARE(calls, 1);
    }

    void widestSamples() {
        VesselState s;
        s.t = 86399;
        s.gnssTime = 86399;
        s.depthM = 9999 * 0.3048;
        s.sogMs = 99.9 * 1852.0 / 3600.0;
        s.stwMs = s.sogMs;
        s.cogRad = 359.0 * 3.14159265358979 / 180.0;
        s.hdgRad = s.cogRad;
        s.waterTempK = 373.15; // 212.0 F, boiling
        s.lat = 47.98;
        s.lon = -122.23;
        s.rpm = 9999;
        for (Field f : {Field::Depth, Field::Sog, Field::Stw, Field::Cog, Field::Heading, Field::WaterTemp,
                        Field::Position, Field::Time, Field::Rpm}) {
            const QString sample = widestSample(f);
            QVERIFY2(!sample.isEmpty(), qPrintable(fieldName(f)));
            const QStringList want = sample.split('\n');
            const QStringList got = formatValue(f, s, UnitPrefs{}).split('\n');
            QVERIFY2(got.size() <= want.size(), qPrintable(fieldName(f)));
            for (int i = 0; i < got.size(); ++i)
                QVERIFY2(got.at(i).size() <= want.at(i).size(), qPrintable(fieldName(f)));
        }
    }
};

QTEST_GUILESS_MAIN(TstSlots)
#include "tst_slots.moc"
