#include "core/Settings.h"
#include "core/Store.h"
#include "core/ViewDraft.h"
#include "core/Views.h"
#include "core/ViewsModel.h"
#include "core/VesselModel.h"
#include <QAbstractItemModelTester>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QUuid>
#include <QtTest>

namespace {
const QString kTwoColumns = QStringLiteral("2x2:0,0,1,2;1,0,1,2");
const QString kQuad = QStringLiteral("2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1");

QVariant role(const QAbstractItemModel& m, int r, const char* name) {
    return m.data(m.index(r, 0), m.roleNames().key(name));
}

QStringList ids(const ViewsModel& m) {
    QStringList l;
    for (const View& v : m.views()) l << v.id;
    return l;
}

QJsonObject rawJson(Store& s, const QString& id) {
    QSqlQuery q(s.db());
    q.prepare("SELECT json FROM views WHERE id=?");
    q.addBindValue(id);
    return q.exec() && q.next() ? QJsonDocument::fromJson(q.value(0).toString().toUtf8()).object() : QJsonObject();
}

int rawOrd(Store& s, const QString& id) {
    QSqlQuery q(s.db());
    q.prepare("SELECT ord FROM views WHERE id=?");
    q.addBindValue(id);
    return q.exec() && q.next() ? q.value(0).toInt() : -1;
}

// A Store (seeded with the shipped views), Settings and VesselModel in a temporary directory, and
// a clock that reads `now`.
struct Env {
    QTemporaryDir dir;
    std::unique_ptr<Store> store;
    std::unique_ptr<Settings> settings;
    VesselModel vessel;
    qint64 now = 1'800'000'000;
    Env() {
        auto s = Store::open(dir.path());
        if (s) store = std::move(*s);
        if (store) settings = std::make_unique<Settings>(*store);
    }
    std::function<qint64()> clock() {
        return [this] { return now; };
    }
};
} // namespace

class TstViewsModel : public QObject {
    Q_OBJECT
private slots:
    void loadsShippedInOrderAndCurrentIsFirst() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QCOMPARE(m.count(), 3);
        QCOMPARE(m.rowCount(), 3);
        QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-fish", "shipped-big"}));
        QCOMPARE(m.currentId(), QStringLiteral("shipped-nav"));
        QCOMPARE(m.favoriteCapacity(), 5);
        QCOMPARE(role(m, 0, "id").toString(), QStringLiteral("shipped-nav"));
        QCOMPARE(role(m, 0, "name").toString(), QStringLiteral("Navigation"));
        QCOMPARE(role(m, 0, "shortName").toString(), QStringLiteral("Nav"));
        QCOMPARE(role(m, 0, "icon").toString(), QStringLiteral("compass"));
        QCOMPARE(role(m, 1, "chart").toString(), QStringLiteral("fish"));
        QCOMPARE(role(m, 2, "chart").toString(), QStringLiteral("none"));
        QVERIFY(role(m, 0, "favorite").toBool());
        QVERIFY(role(m, 2, "onTabBar").toBool());
        const QVariantList slotRows = role(m, 0, "slots").toList();
        QCOMPARE(slotRows.size(), 8);
        QCOMPARE(slotRows[0].toMap(), (QVariantMap{{"id", "TL"}, {"on", true}, {"field", "depth"}, {"sizeMm", 25.0}}));
        QCOMPARE(role(m, 0, "layout").toString(), kTwoColumns);
        QCOMPARE(role(m, 0, "cellFields").toStringList(), (QStringList{"depth", "sog"}));
        QCOMPARE(m.indexOf("shipped-big"), 2);
        QCOMPARE(m.indexOf("nope"), -1);
        QCOMPARE(m.idOfShort("Fish"), QStringLiteral("shipped-fish"));
        QCOMPARE(m.idOfShort("nope"), QString());
        QCOMPARE(m.viewJson("shipped-big").value("name").toString(), QStringLiteral("Big numbers"));
        QVERIFY(m.viewJson("nope").isEmpty());
        QVERIFY(!m.view("nope").has_value());
    }

    void currentFollowsLastViewId() {
        Env e;
        QVERIFY(e.settings);
        e.settings->setLastViewId("shipped-big");
        ViewsModel m(*e.store, *e.settings, e.clock());
        QCOMPARE(m.currentId(), QStringLiteral("shipped-big"));
        QSignalSpy spy(&m, &ViewsModel::currentIdChanged);
        m.setCurrentId("shipped-fish");
        QCOMPARE(m.currentId(), QStringLiteral("shipped-fish"));
        QCOMPARE(e.settings->lastViewId(), QStringLiteral("shipped-fish"));
        QCOMPARE(spy.count(), 1);
        m.setCurrentId("nope"); // unknown: ignored
        QCOMPARE(m.currentId(), QStringLiteral("shipped-fish"));
        QCOMPARE(e.settings->lastViewId(), QStringLiteral("shipped-fish"));
        QCOMPARE(spy.count(), 1);
    }

    void unknownLastViewIdFallsBackToFirst() {
        Env e;
        QVERIFY(e.settings);
        e.settings->setLastViewId("gone");
        ViewsModel m(*e.store, *e.settings, e.clock());
        QCOMPARE(m.currentId(), QStringLiteral("shipped-nav"));
    }

    void addAppendsViewN() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QSignalSpy countSpy(&m, &ViewsModel::countChanged);
        const QString a = m.add();
        const QString b = m.add();
        QCOMPARE(countSpy.count(), 2);
        QCOMPARE(m.count(), 5);
        QCOMPARE(m.indexOf(a), 3);
        QCOMPARE(m.indexOf(b), 4);
        QVERIFY(!QUuid::fromString(b).isNull());
        QVERIFY(!b.startsWith('{'));
        const View va = *m.view(a), vb = *m.view(b);
        QCOMPARE(va.name, QStringLiteral("View 4"));
        QCOMPARE(vb.name, QStringLiteral("View 5"));
        QCOMPARE(va.shortName, QStringLiteral("View4"));
        QCOMPARE(vb.shortName, QStringLiteral("View5"));
        QCOMPARE(vb.chart, ViewChart::Nav);
        QCOMPARE(vb.icon, iconNames().first());
        QVERIFY(!vb.favorite);
        QCOMPARE(vb.slotList.size(), 8);
        for (const ViewSlot& s : vb.slotList) QVERIFY(!s.on);
        QCOMPARE(vb.cells, (ViewCells{kTwoColumns, {Field::Depth, Field::Sog}}));
        QCOMPARE(rawOrd(*e.store, b), 4);

        View renamed = vb;
        renamed.name = "View 6";
        QVERIFY(m.save(renamed));
        const QString c = m.add(); // count + 1 is 6, taken: View 7
        QCOMPARE(m.view(c)->name, QStringLiteral("View 7"));
        QCOMPARE(m.indexOf(c), 5);
    }

    void duplicateInsertsAfter() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        const QString d = m.duplicate("shipped-nav");
        QVERIFY(!d.isEmpty());
        QVERIFY(d != "shipped-nav");
        QCOMPARE(m.indexOf(d), 1);
        const View v = *m.view(d);
        QCOMPARE(v.name, QStringLiteral("Navigation 2"));
        QCOMPARE(v.shortName, QStringLiteral("Naviga"));
        QVERIFY(v.favorite);
        QCOMPARE(v.slotList, m.view("shipped-nav")->slotList);
        QCOMPARE(m.duplicate("nope"), QString());
        ViewsModel again(*e.store, *e.settings, e.clock());
        QCOMPARE(ids(again), ids(m));
    }

    // Review Focus 4: there is always at least one view.
    void removeLastRefused() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QVERIFY(m.remove("shipped-fish"));
        QVERIFY(m.remove("shipped-big"));
        QVERIFY(!m.remove("shipped-nav"));
        QCOMPARE(ids(m), QStringList{"shipped-nav"});
        QVERIFY(!m.remove("nope"));
        ViewsModel again(*e.store, *e.settings, e.clock());
        QCOMPARE(ids(again), QStringList{"shipped-nav"});
    }

    void removeCurrentMovesToNeighbour() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        m.setCurrentId("shipped-fish");
        QVERIFY(m.remove("shipped-fish"));
        QCOMPARE(m.currentId(), QStringLiteral("shipped-big")); // the next one
        QVERIFY(m.remove("shipped-big"));                       // current and last
        QCOMPARE(m.currentId(), QStringLiteral("shipped-nav")); // the previous one
        QCOMPARE(e.settings->lastViewId(), QStringLiteral("shipped-nav"));
    }

    void moveSwapsOrdAndPersists() {
        Env e;
        QVERIFY(e.settings);
        {
            ViewsModel m(*e.store, *e.settings, e.clock());
            m.move("shipped-big", -1);
            QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-big", "shipped-fish"}));
        }
        ViewsModel m(*e.store, *e.settings, e.clock());
        QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-big", "shipped-fish"}));
        m.move("shipped-nav", -1); // first: no-op
        m.move("shipped-fish", 1); // last: no-op
        QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-big", "shipped-fish"}));
        m.move("shipped-nav", 1);
        QCOMPARE(ids(m), (QStringList{"shipped-big", "shipped-nav", "shipped-fish"}));
        ViewsModel again(*e.store, *e.settings, e.clock());
        QCOMPARE(ids(again), ids(m));
    }

    void tabViewsFollowCapacityAndOrder() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        const QString a = m.add(), b = m.add();
        QSignalSpy spy(&m, &ViewsModel::tabViewsChanged);
        m.setFavorite(a, true);
        m.setFavorite(b, true);
        QVERIFY(spy.count() >= 2);
        QVERIFY(m.view(a)->favorite);
        QCOMPARE(m.tabViews().size(), 5);
        m.setFavoriteCapacity(3);
        QCOMPARE(m.favoriteCapacity(), 3);
        const QVariantList tabs = m.tabViews();
        QCOMPARE(tabs.size(), 3);
        QCOMPARE(tabs[0].toMap(), (QVariantMap{{"id", "shipped-nav"}, {"shortName", "Nav"}, {"icon", "compass"}}));
        QCOMPARE(tabs[2].toMap().value("id").toString(), QStringLiteral("shipped-big"));
        QVERIFY(m.onTabBar("shipped-big"));
        QVERIFY(!m.onTabBar(a));
        QVERIFY(!role(m, 3, "onTabBar").toBool());
        m.setFavorite("shipped-fish", false);
        QCOMPARE(m.tabViews()[2].toMap().value("id").toString(), a);
        m.setFavoriteCapacity(0);
        QVERIFY(m.tabViews().isEmpty());
        QVERIFY(!m.onTabBar("shipped-nav"));
    }

    void saveFloorsWhitespaceName() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        View v = *m.view("shipped-fish");
        v.name = "   ";
        v.shortName = "";
        QVERIFY(m.save(v));
        QCOMPARE(m.view("shipped-fish")->name, QStringLiteral("View"));
    }

    void saveUnchangedEmitsNoDataChanged() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        View v = *m.view("shipped-fish");
        QSignalSpy data(&m, &QAbstractItemModel::dataChanged);
        QSignalSpy tabs(&m, &ViewsModel::tabViewsChanged);
        e.now += 10;
        QVERIFY(m.save(v));
        QCOMPARE(data.count(), 0);
        QCOMPARE(tabs.count(), 0);
        v.name = "Other";
        QVERIFY(m.save(v));
        QVERIFY(data.count() >= 1);
        QVERIFY(tabs.count() >= 1);
    }

    void addNonFavoriteEmitsNoTabViewsChanged() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QSignalSpy tabs(&m, &ViewsModel::tabViewsChanged);
        QSignalSpy count(&m, &ViewsModel::countChanged);
        m.add();
        QCOMPARE(tabs.count(), 0);
        QCOMPARE(count.count(), 1);
    }

    void loadIgnoresASlotWithAnOutOfRangeId() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        View v = shippedViews(5)[0];
        v.slotList[3].id = SlotId(9);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("made whole"));
        d.load(v);
        QCOMPARE(d.toView().slotList.size(), 8);
    }

    void saveKeepsOrdAndExtra() {
        Env e;
        QVERIFY(e.settings);
        View x = shippedViews(5)[0];
        x.id = "x";
        QJsonObject json = viewToJson(x);
        json["colour"] = "red";
        QSqlQuery q(e.store->db());
        q.prepare("INSERT INTO views(id, ord, json) VALUES('x', 7, ?)");
        q.addBindValue(QString::fromUtf8(QJsonDocument(json).toJson(QJsonDocument::Compact)));
        QVERIFY(q.exec());
        ViewsModel m(*e.store, *e.settings, e.clock());
        QCOMPARE(m.indexOf("x"), 3);
        View v = *m.view("x");
        v.name = "Renamed";
        v.extra = {};
        QVERIFY(m.save(v));
        const QJsonObject raw = rawJson(*e.store, "x");
        QCOMPARE(raw.value("colour").toString(), QStringLiteral("red"));
        QCOMPARE(raw.value("name").toString(), QStringLiteral("Renamed"));
        QCOMPARE(qint64(raw.value("modified").toDouble()), e.now);
        QCOMPARE(qint64(raw.value("created").toDouble()), qint64(5));
        QCOMPARE(rawOrd(*e.store, "x"), 7);
        QCOMPARE(role(m, 3, "name").toString(), QStringLiteral("Renamed"));

        View unknown = v;
        unknown.id = "nope";
        QVERIFY(!m.save(unknown));
        QVariantMap vm = m.viewJson("x");
        vm["name"] = "By JSON";
        QVERIFY(m.saveJson(vm));
        QCOMPARE(m.view("x")->name, QStringLiteral("By JSON"));
        QCOMPARE(rawJson(*e.store, "x").value("colour").toString(), QStringLiteral("red"));
        vm["id"] = "nope";
        QVERIFY(!m.saveJson(vm));
    }

    // Review Focus 5: names and shorts are cut to their caps; a short is never empty.
    void saveCapsNames() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        View v = *m.view("shipped-fish");
        v.name = QString(30, 'N');
        v.shortName = "ABCDEFGH";
        QVERIFY(m.save(v));
        QCOMPARE(rawJson(*e.store, "shipped-fish").value("name").toString(), QString(24, 'N'));
        QCOMPARE(rawJson(*e.store, "shipped-fish").value("short").toString(), QStringLiteral("ABCDEF"));
        v.name = "Bottom fish";
        v.shortName = "";
        QVERIFY(m.save(v));
        QCOMPARE(m.view("shipped-fish")->shortName, shortFromName("Bottom fish"));
        QCOMPARE(rawJson(*e.store, "shipped-fish").value("short").toString(), QStringLiteral("Bottom"));
        v.name = "";
        v.shortName = "";
        QVERIFY(m.save(v));
        QCOMPARE(m.view("shipped-fish")->name, QStringLiteral("View"));
        QCOMPARE(m.view("shipped-fish")->shortName, QStringLiteral("View"));
        QCOMPARE(rawJson(*e.store, "shipped-fish").value("name").toString(), QStringLiteral("View"));
        QCOMPARE(rawJson(*e.store, "shipped-fish").value("short").toString(), QStringLiteral("View"));
        ViewsModel again(*e.store, *e.settings, e.clock());
        QCOMPARE(again.view("shipped-fish")->name, QStringLiteral("View"));
    }

    // There is always at least one view: an empty list changes nothing.
    void replaceAllRefusesEmpty() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QSignalSpy reset(&m, &QAbstractItemModel::modelReset);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("views: replace refused"));
        m.replaceAll({});
        QCOMPARE(reset.count(), 0);
        QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-fish", "shipped-big"}));
        ViewsModel again(*e.store, *e.settings, e.clock());
        QCOMPARE(again.count(), 3);
    }

    // The model testers check every signal sequence of the mutations.
    void modelTestersPassEveryMutation() {
        Env e;
        QVERIFY(e.settings);
        ViewsModel m(*e.store, *e.settings, e.clock());
        QAbstractItemModelTester mt(&m, QAbstractItemModelTester::FailureReportingMode::QtTest);
        const QString a = m.add();
        const QString d = m.duplicate("shipped-nav");
        m.move(d, 1);
        m.move("shipped-nav", 1);
        m.move(a, -1);
        QVERIFY(m.remove("shipped-fish"));
        m.setFavorite(a, true);
        View v = *m.view(a);
        v.name = "Saved";
        QVERIFY(m.save(v));
        m.replaceAll(shippedViews(1));
        QCOMPARE(m.count(), 3);

        ViewDraft draft(e.vessel, *e.settings);
        auto* slotRows = qobject_cast<QAbstractItemModel*>(draft.slotsModel());
        auto* cells = qobject_cast<QAbstractItemModel*>(draft.cellsModel());
        QAbstractItemModelTester st(slotRows, QAbstractItemModelTester::FailureReportingMode::QtTest);
        QAbstractItemModelTester ct(cells, QAbstractItemModelTester::FailureReportingMode::QtTest);
        draft.load(shippedViews(1)[2]);
        draft.setLayout(kQuad);
        draft.setLayout(kTwoColumns);
        draft.setCellField(0, "rpm");
        draft.setSlot("BL", true, "rpm", 10);
        VesselState s;
        s.depthM = 3;
        e.vessel.setState(s);
        QCOMPARE(cells->rowCount(), 2);
    }

    // A View with a short slot list is made whole on load: eight rows in SlotId order.
    void draftLoadNormalisesShortSlotList() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        View v = shippedViews(5)[0];
        v.slotList = {ViewSlot{SlotId::BR, true, Field::Rpm, 10}, ViewSlot{SlotId::TL, false, Field::Cog, 9},
                      ViewSlot{SlotId::BR, false, Field::Sog, 7}};
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("slot list"));
        d.load(v);
        auto* slotRows = qobject_cast<QAbstractItemModel*>(d.slotsModel());
        QCOMPARE(slotRows->rowCount(), 8);
        const QList<ViewSlot> got = d.toView().slotList;
        QCOMPARE(got.size(), 8);
        for (int i = 0; i < 8; ++i) QCOMPARE(int(got[i].id), i);
        QCOMPARE(got[int(SlotId::TL)], (ViewSlot{SlotId::TL, false, Field::Cog, 9}));
        QCOMPARE(got[int(SlotId::BR)], (ViewSlot{SlotId::BR, true, Field::Rpm, 10})); // first entry wins
        QCOMPARE(got[int(SlotId::Right)], defaultViewSlots()[int(SlotId::Right)]);
        d.setSlot("Right", true, "depth", 12);
        QCOMPARE(d.toView().slotList[int(SlotId::Right)], (ViewSlot{SlotId::Right, true, Field::Depth, 12}));
        QCOMPARE(role(*slotRows, 7, "field").toString(), QStringLiteral("depth"));
    }

    void replaceAllResetsRowsAndCurrent() {
        Env e;
        QVERIFY(e.settings);
        e.settings->setLastViewId("shipped-fish");
        ViewsModel m(*e.store, *e.settings, e.clock());
        QSignalSpy reset(&m, &QAbstractItemModel::modelReset);
        QList<View> list = shippedViews(1);
        list.removeAt(1);
        m.replaceAll(list);
        QCOMPARE(reset.count(), 1);
        QCOMPARE(ids(m), (QStringList{"shipped-nav", "shipped-big"}));
        QCOMPARE(m.currentId(), QStringLiteral("shipped-nav"));
        QCOMPARE(rawOrd(*e.store, "shipped-big"), 1);
        m.replaceAll(shippedViews(1));
        QCOMPARE(m.currentId(), QStringLiteral("shipped-fish"));
    }

    // An edit to a slot keeps that slot's unknown keys; the same values again change nothing.
    void draftSetSlotKeepsSlotExtra() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        View v = shippedViews(5)[0];
        v.slotList[int(SlotId::TR)].extra = QJsonObject{{"glow", true}};
        d.load(v);
        const ViewSlot tr = v.slotList[int(SlotId::TR)];
        d.setSlot("TR", tr.on, fieldName(tr.field), tr.sizeMm);
        QVERIFY(!d.dirty());
        d.setSlot("TR", true, "stw", 20);
        QVERIFY(d.dirty());
        QCOMPARE(d.toView().slotList[int(SlotId::TR)].extra, (QJsonObject{{"glow", true}}));
    }

    void draftRoundTrip() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        const View shipped = shippedViews(5)[0];
        d.load(shipped);
        QCOMPARE(d.toView(), shipped);
        QVERIFY(!d.dirty());
        QCOMPARE(d.id(), QStringLiteral("shipped-nav"));
        QCOMPARE(d.chart(), QStringLiteral("nav"));
        QSignalSpy dirtySpy(&d, &ViewDraft::dirtyChanged);
        d.setSlot("TR", true, "stw", 33.27);
        QVERIFY(d.dirty());
        QCOMPARE(dirtySpy.count(), 1);
        QCOMPARE(d.toView().slotList[int(SlotId::TR)], (ViewSlot{SlotId::TR, true, Field::Stw, 33.3}));
        auto* slotRows = qobject_cast<QAbstractItemModel*>(d.slotsModel());
        QVERIFY(slotRows);
        QCOMPARE(slotRows->rowCount(), 8);
        QCOMPARE(role(*slotRows, 1, "slotId").toString(), QStringLiteral("TR"));
        QCOMPARE(role(*slotRows, 1, "field").toString(), QStringLiteral("stw"));
        QCOMPARE(role(*slotRows, 1, "fieldLabel").toString(), QStringLiteral("STW"));
        QCOMPARE(role(*slotRows, 1, "sizeMm").toDouble(), 33.3);
        d.setSlot("TR", true, "stw", 2);
        QCOMPARE(d.toView().slotList[int(SlotId::TR)].sizeMm, 6.0);
        const View before = d.toView();
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("XX"));
        d.setSlot("XX", true, "stw", 10);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("warp"));
        d.setSlot("TL", true, "warp", 10);
        QCOMPARE(d.toView(), before);

        d.setName(QString(30, 'a'));
        QCOMPARE(d.name(), QString(24, 'a'));
        d.setShortName("");
        QCOMPARE(d.shortName(), QString()); // allowed while typing
        QCOMPARE(d.toView().shortName, shortFromName(QString(24, 'a')));
        d.setShortName("ABCDEFGH");
        QCOMPARE(d.shortName(), QStringLiteral("ABCDEF"));
        d.setChart("fish");
        QCOMPARE(d.toView().chart, ViewChart::Fish);
        d.setFavorite(false);
        QVERIFY(!d.toView().favorite);

        d.loadJson(viewToJson(shipped).toVariantMap());
        QVERIFY(!d.dirty());
        QCOMPARE(d.toView(), shipped);
        QCOMPARE(d.toJson(), viewToJson(shipped).toVariantMap());
        QVERIFY(qobject_cast<QAbstractItemModel*>(d.cellsModel()));
        QCOMPARE(d.property("slots").value<QObject*>(), d.slotsModel());
        QCOMPARE(d.property("cells").value<QObject*>(), d.cellsModel());
    }

    void draftLayoutKeepsFieldsByOrder() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        d.load(shippedViews(5)[0]);
        auto* cells = qobject_cast<QAbstractItemModel*>(d.cellsModel());
        QCOMPARE(cells->rowCount(), 2);
        d.setLayout(kQuad);
        QVERIFY(d.dirty());
        QCOMPARE(d.layout(), kQuad);
        QCOMPARE(d.toView().cells.fields, (QList<Field>{Field::Depth, Field::Sog, Field::Stw, Field::Cog}));
        QCOMPARE(cells->rowCount(), 4);
        QCOMPARE(role(*cells, 3, "field").toString(), QStringLiteral("cog"));
        d.setCellField(1, "rpm");
        QCOMPARE(role(*cells, 1, "fieldLabel").toString(), QStringLiteral("RPM"));
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("cell"));
        d.setCellField(4, "rpm");
        d.setLayout(kTwoColumns);
        QCOMPARE(d.toView().cells.fields, (QList<Field>{Field::Depth, Field::Rpm}));
        QCOMPARE(cells->rowCount(), 2);
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("2x3:0,0,2,1"));
        d.setLayout("2x3:0,0,2,1");
        QCOMPARE(d.layout(), kTwoColumns);
    }

    // Each slot row carries its field's widest sample, for the page's size clamp.
    void draftSlotsHaveWidestSample() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        d.load(shippedViews(5)[0]);
        auto* slotRows = qobject_cast<QAbstractItemModel*>(d.slotsModel());
        QCOMPARE(role(*slotRows, 0, "widestSample").toString(), widestSample(Field::Depth));
        d.setSlot("TL", true, "pos", 14);
        QCOMPARE(role(*slotRows, 0, "widestSample").toString(), widestSample(Field::Position));
    }

    void draftFormattedFollowsVesselAndUnits() {
        Env e;
        QVERIFY(e.settings);
        ViewDraft d(e.vessel, *e.settings);
        d.load(shippedViews(5)[0]);
        auto* slotRows = qobject_cast<QAbstractItemModel*>(d.slotsModel());
        auto* cells = qobject_cast<QAbstractItemModel*>(d.cellsModel());
        QSignalSpy changed(slotRows, &QAbstractItemModel::dataChanged);
        QSignalSpy cellsChanged(cells, &QAbstractItemModel::dataChanged);
        VesselState s;
        s.depthM = 3;
        e.vessel.setLive(true);
        e.vessel.setState(s);
        QVERIFY(changed.count() >= 1);
        QVERIFY(cellsChanged.count() >= 1);
        QCOMPARE(role(*slotRows, 0, "formatted").toString(), QStringLiteral("9.8"));
        QCOMPARE(role(*slotRows, 0, "unit").toString(), QStringLiteral("ft"));
        QCOMPARE(role(*cells, 0, "formatted").toString(), QStringLiteral("9.8"));
        QCOMPARE(role(*cells, 0, "unit").toString(), QStringLiteral("ft"));
        const int before = changed.count(), cellsBefore = cellsChanged.count();
        e.settings->setDepthUnit("m");
        QVERIFY(changed.count() > before);
        QVERIFY(cellsChanged.count() > cellsBefore);
        QCOMPARE(role(*slotRows, 0, "formatted").toString(), QStringLiteral("3.0"));
        QCOMPARE(role(*slotRows, 0, "unit").toString(), QStringLiteral("m"));
        QCOMPARE(role(*cells, 0, "formatted").toString(), QStringLiteral("3.0"));
        QCOMPARE(role(*cells, 0, "unit").toString(), QStringLiteral("m"));
        QCOMPARE(slotRows->property("fieldChoices").toList(), fieldChoices());
        QCOMPARE(cells->property("fieldChoices").toList(), fieldChoices());
    }
};

QTEST_GUILESS_MAIN(TstViewsModel)
#include "tst_viewsmodel.moc"
