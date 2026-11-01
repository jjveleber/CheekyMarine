#include "core/Views.h"
#include <QJsonDocument>
#include <QtTest>

namespace {
QJsonObject parse(const char* json) { return QJsonDocument::fromJson(json).object(); }
QJsonArray parseArray(const char* json) { return QJsonDocument::fromJson(json).array(); }
const QString kTwoCols = QStringLiteral("2x2:0,0,1,2;1,0,1,2");
} // namespace

class TstViews : public QObject {
    Q_OBJECT
private slots:
    void chartNames() {
        for (ViewChart c : {ViewChart::Nav, ViewChart::Fish, ViewChart::None})
            QCOMPARE(viewChartFromName(viewChartName(c)), std::optional<ViewChart>(c));
        QCOMPARE(viewChartName(ViewChart::Nav), QStringLiteral("nav"));
        QCOMPARE(viewChartName(ViewChart::Fish), QStringLiteral("fish"));
        QCOMPARE(viewChartName(ViewChart::None), QStringLiteral("none"));
        QVERIFY(!viewChartFromName(u"warp").has_value());
    }

    void shippedViews() {
        const QList<View> v = ::shippedViews(1000);
        QCOMPARE(v.size(), 3);
        QCOMPARE(v[0].id, QStringLiteral("shipped-nav"));
        QCOMPARE(v[1].id, QStringLiteral("shipped-fish"));
        QCOMPARE(v[2].id, QStringLiteral("shipped-big"));
        for (const View& x : v) {
            QVERIFY(x.favourite);
            QCOMPARE(x.created, qint64(1000));
            QCOMPARE(x.modified, qint64(1000));
            QCOMPARE(x.slotList, defaultViewSlots());
            QCOMPARE(x.cells.layout, kTwoCols);
            QCOMPARE(x.cells.fields, (QList<Field>{Field::Depth, Field::Sog}));
        }
        QCOMPARE(v[0].name, QStringLiteral("Navigation"));
        QCOMPARE(v[0].chart, ViewChart::Nav);
        QCOMPARE(v[0].shortName, QStringLiteral("Nav"));
        QCOMPARE(v[1].shortName, QStringLiteral("Fish"));
        QCOMPARE(v[0].icon, QStringLiteral("compass"));
        QCOMPARE(v[0].slotList[0], (ViewSlot{SlotId::TL, true, Field::Depth, 25}));
        QCOMPARE(v[0].slotList[1], (ViewSlot{SlotId::TR, true, Field::Sog, 25}));
        for (int i = 2; i < 8; ++i) QVERIFY(!v[0].slotList[i].on);
        QCOMPARE(v[1].name, QStringLiteral("Fishing"));
        QCOMPARE(v[1].chart, ViewChart::Fish);
        QCOMPARE(v[1].icon, QStringLiteral("fish"));
        QCOMPARE(v[2].name, QStringLiteral("Big numbers"));
        QCOMPARE(v[2].shortName, QStringLiteral("Big #"));
        QCOMPARE(v[2].icon, QStringLiteral("hash"));
        QCOMPARE(v[2].chart, ViewChart::None);
    }

    void jsonRoundTrip() {
        for (const View& v : ::shippedViews(1234567890123LL)) QCOMPARE(viewFromJson(viewToJson(v)), v);
    }

    void unknownKeysSurvive() {
        const QJsonObject o = parse(R"({"id":"a","name":"X","colour":"red","slots":[{"id":"TL","on":true,"glow":true}]})");
        const QJsonObject back = viewToJson(viewFromJson(o));
        QCOMPARE(back.value("colour").toString(), QStringLiteral("red"));
    }

    void badFieldsTakeDefaults() {
        const QJsonObject o = parse(R"({"id":"a","name":"X","chart":"3d","icon":"dragon",
            "cells":{"layout":"2x3:0,0,2,1","fields":["warp","sog","x"]},
            "slots":[{"id":"BL","sizeMm":2},{"id":"BR","size":"large"}]})");
        const View v = viewFromJson(o);
        QCOMPARE(v.chart, ViewChart::Nav);
        QCOMPARE(v.icon, QStringLiteral("anchor"));
        QCOMPARE(v.cells.layout, kTwoCols);
        QCOMPARE(v.cells.fields, (QList<Field>{Field::Depth, Field::Sog}));
        QCOMPARE(v.slotList[int(SlotId::BL)].sizeMm, 6.0);
        QCOMPARE(v.slotList[int(SlotId::BR)].sizeMm, 25.0);
    }

    void shortAndDuplicateNames() {
        QCOMPARE(shortFromName("View 12"), QStringLiteral("View12"));
        QCOMPARE(shortFromName("Navigation"), QStringLiteral("Naviga"));
        QCOMPARE(shortFromName("   "), QStringLiteral("View"));
        QCOMPARE(duplicateName(QString(24, 'a')).size(), 24);
        QCOMPARE(duplicateName("Fishing"), QStringLiteral("Fishing 2"));
    }

    void plan3Conversion() {
        const QJsonArray slotsJson = parseArray(R"([{"id":"TL","on":true,"field":"pos","size":"medium"},
            {"id":"Top","on":true,"field":"time","size":"small"}])");
        QList<View> v = viewsFromPlan3(slotsJson, {"depth", "sog", "wtemp", "stw"}, 5);
        QCOMPARE(v.size(), 3);
        QCOMPARE(v[0].slotList[int(SlotId::TL)], (ViewSlot{SlotId::TL, true, Field::Position, 14}));
        QCOMPARE(v[0].slotList[int(SlotId::Top)], (ViewSlot{SlotId::Top, true, Field::Time, 8}));
        QCOMPARE(v[0].slotList[int(SlotId::TR)], (ViewSlot{SlotId::TR, true, Field::Sog, 25}));
        QCOMPARE(v[2].cells.layout, QStringLiteral("2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"));
        QCOMPARE(v[2].cells.fields, (QList<Field>{Field::Depth, Field::Sog, Field::WaterTemp, Field::Stw}));

        v = viewsFromPlan3(slotsJson, {"depth", "cog", "rpm"}, 5);
        QCOMPARE(v[2].cells.layout, QStringLiteral("3x2:0,0,1,2;1,0,1,2;2,0,1,2"));
        QCOMPARE(v[2].cells.fields, (QList<Field>{Field::Depth, Field::Cog, Field::Rpm}));

        v = viewsFromPlan3(slotsJson, {"depth"}, 5);
        QCOMPARE(v[2].cells.layout, kTwoCols);
        QCOMPARE(v[2].cells.fields, (QList<Field>{Field::Depth, Field::Sog}));

        v = viewsFromPlan3(slotsJson, {"depth", "sog", "stw", "cog", "hdg"}, 5);
        QCOMPARE(v[2].cells.fields.size(), 4);

        for (const View& x : v) QCOMPARE(viewFromJson(viewToJson(x)), x);
    }

    void favouriteCapacityValues() {
        QCOMPARE(favouriteCapacity(129.7), 5);
        QCOMPARE(favouriteCapacity(136), 5);
        QCOMPARE(favouriteCapacity(100), 3);
        QCOMPARE(favouriteCapacity(62), 1);
        QCOMPARE(favouriteCapacity(61), 0);
        QCOMPARE(favouriteCapacity(10), 0);
    }

    void iconNamesSixteenAnchorFirst() {
        QCOMPARE(iconNames().size(), 16);
        QCOMPARE(iconNames().first(), QStringLiteral("anchor"));
        QVERIFY(iconNames().contains("home"));
    }
};

QTEST_GUILESS_MAIN(TstViews)
#include "tst_views.moc"
