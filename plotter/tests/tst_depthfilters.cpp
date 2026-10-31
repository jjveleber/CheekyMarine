#include "core/DepthFilters.h"
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QtTest>

namespace {
// QVERIFY2 evaluates its message eagerly, and expected::error() on a value is undefined.
template <class R> QByteArray errText(const R& r) { return r.has_value() ? QByteArray() : r.error().toLocal8Bit(); }
QJsonObject load(const QString& name) {
    QFile f(QStringLiteral(PLOTTER_FIXTURES "/styles/") + name + QStringLiteral(".json"));
    if (!f.open(QIODevice::ReadOnly)) return {};
    return QJsonDocument::fromJson(f.readAll()).object();
}
// Parses one JSON value; tests compare QJsonValues (numbers as doubles), never text.
QJsonValue json(const QByteArray& text) {
    return QJsonDocument::fromJson("[" + text + "]").array().at(0);
}
QJsonValue originalFilter(const QJsonObject& style, const QString& id) {
    for (const auto& l : style["layers"].toArray())
        if (l.toObject()["id"].toString() == id) return l.toObject()["filter"];
    return QJsonValue::Undefined;
}
QJsonObject withFilter(QJsonObject style, const QString& id, const QJsonValue& filter) {
    QJsonArray layers = style["layers"].toArray();
    for (int i = 0; i < layers.size(); ++i) {
        QJsonObject l = layers[i].toObject();
        if (l["id"].toString() == id) {
            l["filter"] = filter;
            layers[i] = l;
        }
    }
    style["layers"] = layers;
    return style;
}
const QList<double> kValdco{0, 0.9, 1.8, 3.6, 5, 5.4, 9.1, 10, 18.2, 20, 27.4, 30};
}

class TstDepthFilters : public QObject {
    Q_OBJECT
private slots:
    void safetyContourRule() {
        QCOMPARE(safetyContour(kValdco, 3.048), 3.6);
        QCOMPARE(safetyContour(kValdco, 3.6), 3.6);
        QCOMPARE(safetyContour(kValdco, 31), 31.0);
        QCOMPARE(safetyContour({}, 3.048), 3.048);
    }

    void navTarget_data() {
        QTest::addColumn<QString>("name");
        for (const char* n : {"nav-day", "nav-dusk", "nav-night"}) QTest::newRow(n) << QString(n);
    }
    void navTarget() {
        QFETCH(QString, name);
        const QJsonObject s = load(name);
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY2(r.has_value(), errText(r).constData());
        QCOMPARE(r->size(), 9);
        QCOMPARE(r->value("depare-medium"),
                 json(R"(["all",[">=",["to-number",["get","DRVAL1"]],4.0],["<",["to-number",["get","DRVAL1"]],12.0]])"));
        QCOMPARE(r->value("depare-shallow"),
                 json(R"(["all",[">=",["to-number",["get","DRVAL1"]],1.5],["<",["to-number",["get","DRVAL1"]],4.0]])"));
        QCOMPARE(r->value("depare-vshallow"), json(R"(["<",["to-number",["get","DRVAL1"]],1.5])"));
        QCOMPARE(r->value("depare-deep"), json(R"([">=",["to-number",["get","DRVAL1"]],12.0])"));
        QCOMPARE(r->value("depcnt-safety"), json(R"(["==",["to-number",["get","VALDCO"]],5])"));
        QCOMPARE(r->value("soundg-deep"), json(R"([">=",["to-number",["get","depth"]],4.0])"));
        QCOMPARE(r->value("soundg-shallow"), json(R"(["<",["to-number",["get","depth"]],4.0])"));
        const QByteArray hazard =
            R"(["any",["!",["has","VALSOU"]],["<",["to-number",["get","VALSOU"]],4.0],["in",["coalesce",["get","WATLEV"],0],["literal",[1,2,4,5]]]])";
        QCOMPARE(r->value("hazard-danger"), json(hazard));
        QCOMPARE(r->value("hazard-danger-outline"), json(hazard));
    }

    void identityOnAllSixStyles_data() {
        QTest::addColumn<QString>("name");
        QTest::addColumn<int>("count");
        for (const char* n : {"nav-day", "nav-dusk", "nav-night"}) QTest::newRow(n) << QString(n) << 9;
        for (const char* n : {"fish-day", "fish-dusk", "fish-night"}) QTest::newRow(n) << QString(n) << 2;
    }
    void identityOnAllSixStyles() {
        QFETCH(QString, name);
        QFETCH(int, count);
        const QJsonObject s = load(name);
        const QJsonObject cm = s["metadata"].toObject()["cheekymarine"].toObject();
        const QJsonObject d = cm["depths"].toObject();
        auto r = depthFilters(s, {d["shallow_m"].toDouble(), d["safety_m"].toDouble(), d["deep_m"].toDouble()},
                              cm["safety_contour_m"].toDouble());
        QVERIFY2(r.has_value(), errText(r).constData());
        QCOMPARE(r->size(), count);
        for (auto it = r->begin(); it != r->end(); ++it) QCOMPARE(it.value(), originalFilter(s, it.key()));
        if (name.startsWith("fish")) {
            QVERIFY(r->contains("hazard-danger"));
            QVERIFY(r->contains("hazard-danger-outline"));
        }
    }

    void fishTargetChangesHazardOnly_data() {
        QTest::addColumn<QString>("name");
        for (const char* n : {"fish-day", "fish-dusk", "fish-night"}) QTest::newRow(n) << QString(n);
    }
    void fishTargetChangesHazardOnly() {
        QFETCH(QString, name);
        const QJsonObject s = load(name);
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY2(r.has_value(), errText(r).constData());
        QCOMPARE(r->size(), 2);
        const QByteArray hazard =
            R"(["any",["!",["has","VALSOU"]],["<",["to-number",["get","VALSOU"]],4.0],["in",["coalesce",["get","WATLEV"],0],["literal",[1,2,4,5]]]])";
        QCOMPARE(r->value("hazard-danger"), json(hazard));
        QCOMPARE(r->value("hazard-danger-outline"), json(hazard));
    }

    void unmappableLiteralErrors() {
        const QJsonObject s = withFilter(load("nav-day"), "depare-deep",
                                         json(R"([">=",["to-number",["get","DRVAL1"]],7.7])"));
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY(!r.has_value());
        QVERIFY2(r.error().contains("depare-deep") && r.error().contains("7.7"), errText(r).constData());
    }

    void safetyContourValueOutsideDepcntSafetyErrors() {
        // 3.6 is the style's safety_contour_m; only depcnt-safety may carry it.
        const QJsonObject s = withFilter(load("nav-day"), "soundg-deep",
                                         json(R"([">=",["to-number",["get","depth"]],3.6])"));
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY(!r.has_value());
        QVERIFY2(r.error().contains("soundg-deep") && r.error().contains("3.6"), errText(r).constData());
    }

    void depthReadOutsidePlainComparisonErrors_data() {
        QTest::addColumn<QByteArray>("filter");
        QTest::newRow("step") << QByteArray(R"(["step",["to-number",["get","depth"]],false,3.048,true])");
        QTest::newRow("match") << QByteArray(R"(["match",["get","DRVAL1"],9.144,true,false])");
        QTest::newRow("arithmetic") << QByteArray(R"(["<",["+",["get","VALSOU"],1],3.048])");
        QTest::newRow("4-arg comparison") << QByteArray(R"(["<",["get","depth"],3.048,["collator",{}]])");
        QTest::newRow("to-number default") << QByteArray(R"([">=",["to-number",["get","depth"],0],3.048])");
    }
    void depthReadOutsidePlainComparisonErrors() {
        QFETCH(QByteArray, filter);
        const QJsonObject s = withFilter(load("nav-day"), "soundg-deep", json(filter));
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY(!r.has_value());
        QVERIFY2(r.error().contains("soundg-deep"), errText(r).constData());
    }

    void listedLayerMissingFromStyleErrors() {
        QJsonObject s = load("nav-day");
        QJsonArray layers;
        for (const auto& l : s["layers"].toArray())
            if (l.toObject()["id"].toString() != "depare-medium") layers.append(l);
        s["layers"] = layers;
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY(!r.has_value());
        QVERIFY2(r.error().contains("depare-medium"), errText(r).constData());
    }

    void literalOnLeftSideIsMapped() {
        const QJsonObject s = withFilter(load("nav-day"), "soundg-deep", json(R"(["<",3.048,["to-number",["get","depth"]]])"));
        auto r = depthFilters(s, {1.5, 4.0, 12.0}, 5);
        QVERIFY2(r.has_value(), errText(r).constData());
        QCOMPARE(r->value("soundg-deep"), json(R"(["<",4.0,["to-number",["get","depth"]]])"));
    }
};

QTEST_APPLESS_MAIN(TstDepthFilters)
#include "tst_depthfilters.moc"
