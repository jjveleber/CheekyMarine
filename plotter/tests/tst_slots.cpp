#include "core/NumbersModel.h"
#include "core/Settings.h"
#include "core/Slots.h"
#include "core/Store.h"
#include "core/Units.h"
#include "core/VesselModel.h"
#include <QJsonDocument>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QtTest>

namespace {
QJsonArray parse(const char* json) { return QJsonDocument::fromJson(json).array(); }

QString row(const QAbstractItemModel& m, int r, const char* role) {
    const QHash<int, QByteArray> names = m.roleNames();
    return m.data(m.index(r, 0), names.key(role)).toString();
}

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

    void slotsModelReadsAndWritesSettings() {
        Env e;
        QVERIFY(e.settings);
        e.settings->setSlotsJson(parse(R"([{"id":"BR","on":true,"field":"rpm","size":"small"}])"));
        SlotsModel m(*e.settings, e.vessel);
        QCOMPARE(m.rowCount(), 8);
        QCOMPARE(row(m, 3, "slotId"), QStringLiteral("BR"));
        QCOMPARE(m.data(m.index(3, 0), SlotsModel::OnRole).toBool(), true);
        QCOMPARE(row(m, 3, "field"), QStringLiteral("rpm"));
        QCOMPARE(row(m, 3, "fieldLabel"), QStringLiteral("RPM"));
        QCOMPARE(row(m, 3, "size"), QStringLiteral("small"));
        QCOMPARE(row(m, 0, "formatted"), QStringLiteral("--"));
        QCOMPARE(row(m, 0, "unit"), QStringLiteral("ft"));

        QSignalSpy changed(&m, &QAbstractItemModel::dataChanged);
        m.setSlot("Left", true, "cog", "large");
        QCOMPARE(changed.count(), 1);
        QCOMPARE(m.slotConfigs().at(6), (SlotConfig{SlotId::Left, true, Field::Cog, SlotSize::Large}));
        QCOMPARE(slotsFromJson(e.settings->slotsJson().toArray()), m.slotConfigs());

        // Rejected: unknown id, field or size.
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("slots: rejected"));
        m.setSlot("Middle", true, "cog", "large");
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("slots: rejected"));
        m.setSlot("TL", true, "warp", "large");
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("slots: rejected"));
        m.setSlot("TL", true, "depth", "huge");
        QCOMPARE(m.slotConfigs().at(0), defaultSlots().at(0));

        // A second model on the same settings sees the stored slots.
        SlotsModel again(*e.settings, e.vessel);
        QCOMPARE(again.slotConfigs(), m.slotConfigs());
    }

    void slotsModelFormattedFollowsVesselAndUnits() {
        Env e;
        SlotsModel m(*e.settings, e.vessel);
        QSignalSpy changed(&m, &QAbstractItemModel::dataChanged);
        VesselState s;
        s.depthM = 12 * 0.3048;
        s.sogMs = 5.2 * 1852.0 / 3600.0;
        e.vessel.setLive(true);
        e.vessel.setState(s);
        QVERIFY(changed.count() >= 1);
        QCOMPARE(row(m, 0, "formatted"), QStringLiteral("12"));
        QCOMPARE(row(m, 1, "formatted"), QStringLiteral("5.2"));
        QCOMPARE(row(m, 1, "unit"), QStringLiteral("kn"));
        const int before = changed.count();
        e.settings->setDepthUnit("m");
        QVERIFY(changed.count() > before);
        QCOMPARE(row(m, 0, "formatted"), QStringLiteral("3.7"));
        QCOMPARE(row(m, 0, "unit"), QStringLiteral("m"));
        e.settings->setSpeedUnit("kmh");
        QCOMPARE(row(m, 1, "unit"), QStringLiteral("km/h"));
    }

    // A newer app's extra slot, per-slot keys and field name survive an edit of one slot (Review Focus 5, R34).
    void unknownSlotsAndKeysSurviveSave() {
        Env e;
        QVERIFY(e.settings);
        const QJsonArray stored = parse(R"([
            {"id":"TL","on":true,"field":"depth","size":"large","colour":"red"},
            {"id":"Centre","on":true,"field":"aws","size":"small"},
            {"id":"TR","on":true,"field":"sog","size":"large","colour":"blue"},
            {"id":"BL","on":false,"field":"cog","size":"medium","blink":true},
            {"id":"BR","on":false,"field":"wtemp","size":"medium","blink":false},
            {"id":"Top","on":false,"field":"aws","size":"small","x":1},
            {"id":"Bottom","on":false,"field":"pos","size":"small","x":2},
            {"id":"Left","on":false,"field":"stw","size":"medium","x":3},
            {"id":"Right","on":false,"field":"hdg","size":"medium","x":4}])");
        e.settings->setSlotsJson(stored);
        SlotsModel m(*e.settings, e.vessel);
        m.setSlot("BL", true, "rpm", "large");
        QJsonArray want = stored;
        QJsonObject bl = want.at(3).toObject();
        bl["on"] = true;
        bl["field"] = "rpm";
        bl["size"] = "large";
        want[3] = bl;
        QCOMPARE(e.settings->slotsJson().toArray(), want);
    }

    // Picking the default field over a newer app's unknown one stores the default's name.
    void choosingDefaultOverUnknownFieldIsSaved() {
        Env e;
        QVERIFY(e.settings);
        e.settings->setSlotsJson(parse(R"([{"id":"Top","on":false,"field":"aws","size":"small","x":1}])"));
        SlotsModel m(*e.settings, e.vessel);
        QCOMPARE(m.slotConfigs().at(4).field, Field::Time); // aws is unknown here: the slot default
        m.setSlot("Top", false, "time", "small");
        QCOMPARE(e.settings->slotsJson().toArray(),
                 parse(R"([{"id":"Top","on":false,"field":"time","size":"small","x":1}])"));
    }

    // Each unit setting refreshes the formatted and unit roles of both models.
    void unitSettingsRefreshBothModels_data() {
        QTest::addColumn<QString>("setting");
        for (const char* s : {"depthUnit", "speedUnit", "tempUnit", "applyDepthOffset"}) QTest::newRow(s) << QString(s);
    }
    void unitSettingsRefreshBothModels() {
        QFETCH(QString, setting);
        Env e;
        QVERIFY(e.settings);
        SlotsModel m(*e.settings, e.vessel);
        NumbersModel n(*e.settings, e.vessel);
        QSignalSpy slotsChanged(&m, &QAbstractItemModel::dataChanged);
        QSignalSpy numbersChanged(&n, &QAbstractItemModel::dataChanged);
        if (setting == "depthUnit") e.settings->setDepthUnit("m");
        if (setting == "speedUnit") e.settings->setSpeedUnit("kmh");
        if (setting == "tempUnit") e.settings->setTempUnit("C");
        if (setting == "applyDepthOffset") e.settings->setApplyDepthOffset(false);
        QCOMPARE(slotsChanged.count(), 1);
        QCOMPARE(numbersChanged.count(), 1);
        const QList<int> roles{SlotsModel::FormattedRole, SlotsModel::UnitRole};
        QCOMPARE(slotsChanged.at(0).at(2).value<QList<int>>(), roles);
        QCOMPARE(numbersChanged.at(0).at(2).value<QList<int>>(), (QList<int>{NumbersModel::FormattedRole, NumbersModel::UnitRole}));
    }

    void slotsModelReloadsOnExternalChange() {
        Env e;
        SlotsModel m(*e.settings, e.vessel);
        e.settings->setSlotsJson(parse(R"([{"id":"Top","on":true,"field":"time","size":"medium"}])"));
        QCOMPARE(m.slotConfigs().at(4), (SlotConfig{SlotId::Top, true, Field::Time, SlotSize::Medium}));
    }

    void numbersDefaults() {
        Env e;
        NumbersModel n(*e.settings, e.vessel);
        QCOMPARE(n.count(), 2);
        QCOMPARE(n.rowCount(), 2);
        QCOMPARE(n.fields(), (QList<Field>{Field::Depth, Field::Sog}));
        QCOMPARE(row(n, 0, "field"), QStringLiteral("depth"));
        QCOMPARE(row(n, 0, "fieldLabel"), QStringLiteral("Depth"));
        QCOMPARE(row(n, 1, "formatted"), QStringLiteral("--"));
        QCOMPARE(row(n, 1, "unit"), QStringLiteral("kn"));
    }

    void numbersCountAndFields() {
        Env e;
        NumbersModel n(*e.settings, e.vessel);
        QSignalSpy count(&n, &NumbersModel::countChanged);
        n.setCount(4);
        QCOMPARE(count.count(), 1);
        QCOMPARE(n.fields(), (QList<Field>{Field::Depth, Field::Sog, Field::Cog, Field::Stw}));
        QCOMPARE(e.settings->bigNumbers(), (QStringList{"depth", "sog", "cog", "stw"}));
        n.setField(2, "wtemp");
        QCOMPARE(n.fields().at(2), Field::WaterTemp);
        QCOMPARE(e.settings->bigNumbers(), (QStringList{"depth", "sog", "wtemp", "stw"}));
        n.setCount(3);
        QCOMPARE(e.settings->bigNumbers(), (QStringList{"depth", "sog", "wtemp"}));
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("numbers: rejected"));
        n.setCount(5);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("numbers: rejected"));
        n.setCount(1);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("numbers: rejected"));
        n.setField(3, "cog");
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("numbers: rejected"));
        n.setField(0, "warp");
        QCOMPARE(n.count(), 3);
        QCOMPARE(n.fields(), (QList<Field>{Field::Depth, Field::Sog, Field::WaterTemp}));
    }

    void numbersSanitiseStoredList() {
        Env e;
        e.settings->setBigNumbers({"warp", "cog", "rpm", "pos", "time", "hdg"});
        NumbersModel n(*e.settings, e.vessel);
        QCOMPARE(n.fields(), (QList<Field>{Field::Depth, Field::Cog, Field::Rpm, Field::Position}));
        e.settings->setBigNumbers({"stw"});
        QCOMPARE(n.fields(), (QList<Field>{Field::Stw, Field::Sog}));
    }

    void numbersFormattedFollowsVessel() {
        Env e;
        NumbersModel n(*e.settings, e.vessel);
        QSignalSpy changed(&n, &QAbstractItemModel::dataChanged);
        VesselState s;
        s.depthM = 3 * 0.3048;
        e.vessel.setLive(true);
        e.vessel.setState(s);
        QVERIFY(changed.count() >= 1);
        QCOMPARE(row(n, 0, "formatted"), QStringLiteral("3.0"));
    }
};

QTEST_GUILESS_MAIN(TstSlots)
#include "tst_slots.moc"
