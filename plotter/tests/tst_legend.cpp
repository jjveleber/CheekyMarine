#include "core/Legend.h"
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSet>
#include <QtTest>

namespace {
QJsonObject fixture(const QString& name) {
    QFile f(QStringLiteral(PLOTTER_FIXTURES "/styles/") + name + QStringLiteral(".json"));
    if (!f.open(QIODevice::ReadOnly)) return {};
    return QJsonDocument::fromJson(f.readAll()).object();
}

QStringList ids(const QVariantList& categories) {
    QStringList out;
    for (const QVariant& c : categories) out << c.toMap()["id"].toString();
    return out;
}

QVariantMap category(const QVariantList& categories, const QString& id) {
    for (const QVariant& c : categories)
        if (c.toMap()["id"].toString() == id) return c.toMap();
    return {};
}

QVariantList allRows(const QVariantList& categories) {
    QVariantList rows;
    for (const QVariant& c : categories) rows += c.toMap()["rows"].toList();
    return rows;
}

QVariantMap rowLabelled(const QVariantList& rows, const QString& label) {
    for (const QVariant& r : rows)
        if (r.toMap()["label"].toString() == label) return r.toMap();
    return {};
}

QColor col(const std::optional<QColor>& c) { return c.value_or(QColor()); }

const QVariantList kSeabed{QVariantMap{{"abbr", "S"}, {"meaning", "sand"}, {"kind", "material"}}};
} // namespace

class TstLegend : public QObject {
    Q_OBJECT
private slots:
    void init() { QTest::failOnWarning(QRegularExpression(".*")); }

    void styleColourLiteralAndExpressions() {
        const QJsonObject nav = fixture("nav-day"), fish = fixture("fish-day");
        QVERIFY(!nav.isEmpty() && !fish.isEmpty());
        QCOMPARE(col(styleColour(nav, "depare-deep", "fill-color")), QColor("#F4EEE2"));
        QCOMPARE(col(styleColour(fish, "band-fill", "fill-color", 0)), QColor("#8EC3E6"));
        QCOMPARE(col(styleColour(fish, "band-fill", "fill-color", 1)), QColor("#B8DCF2"));
        QCOMPARE(col(styleColour(fish, "band-fill", "fill-color", 2)), QColor("#DCEEF9"));
        QCOMPARE(col(styleColour(fish, "band-fill", "fill-color", 3)), QColor("#F4EEE2"));
        QCOMPARE(col(styleColour(fish, "band-fill", "fill-color", -1)), QColor("#F4EEE2"));
        QVERIFY(!styleColour(fish, "band-fill", "fill-color", 4));
        QCOMPARE(col(styleColour(nav, "navaid", "icon-color", -1)), QColor("#6B7A82")); // CHGRD
        QCOMPARE(col(styleColour(nav, "navaid", "icon-color", 0)), QColor("#FFFFFF"));
        QVERIFY(!styleColour(nav, "no-such-layer", "fill-color"));
        QVERIFY(!styleColour(nav, "depare-deep", "line-color"));
    }

    void everyStyleLayerHasALegendRow_data() {
        QTest::addColumn<QString>("name");
        for (const char* n : {"nav-day", "nav-dusk", "nav-night", "fish-day", "fish-dusk", "fish-night"})
            QTest::newRow(n) << QString::fromLatin1(n);
    }
    void everyStyleLayerHasALegendRow() {
        QFETCH(QString, name);
        const QJsonObject style = fixture(name);
        QVERIFY(!style.isEmpty());
        const QStringList parts = name.split('-');
        const QVariantList cats = legendCategories(parts[0], style, parts[1], kSeabed);
        QSet<QString> covered;
        for (const QVariant& r : allRows(cats))
            for (const QVariant& l : r.toMap()["layers"].toList()) covered.insert(l.toString());
        for (const QJsonValue& l : style["layers"].toArray()) {
            const QString id = l.toObject()["id"].toString();
            QVERIFY2(covered.contains(id), qPrintable(name + ": no legend row for layer " + id));
        }
    }

    void fishHasNoNavaidsOrSoundings() {
        const QVariantList cats = legendCategories("fish", fixture("fish-day"), "day", kSeabed);
        QVERIFY(!ids(cats).contains("navaids"));
        for (const QVariant& r : allRows(cats))
            QVERIFY(!r.toMap()["layers"].toList().contains(QStringLiteral("soundg-deep")));
    }

    void categoryOrder() {
        QCOMPARE(ids(legendCategories("nav", fixture("nav-day"), "day", kSeabed)),
                 QStringList({"ais", "navaids", "lights", "hazards", "depths", "seabed"}));
        QCOMPARE(ids(legendCategories("fish", fixture("fish-day"), "day", kSeabed)),
                 QStringList({"ais", "lights", "hazards", "depths", "seabed"}));
        const QVariantList cats = legendCategories("nav", fixture("nav-day"), "day", kSeabed);
        QCOMPARE(category(cats, "depths")["title"].toString(), QStringLiteral("Depths, areas and lines"));
        QCOMPARE(category(cats, "ais")["title"].toString(), QStringLiteral("AIS targets"));
    }

    void hazardSpritesFollowPalette() {
        const QVariantList cats = legendCategories("nav", fixture("nav-night"), "night", kSeabed);
        const QVariantList rows = category(cats, "hazards")["rows"].toList();
        const QVariantMap rock = rowLabelled(rows, "Rock");
        QCOMPARE(rock["sprite"].toString(), QStringLiteral("hazard-rock-night"));
        QCOMPARE(rock["kind"].toString(), QStringLiteral("sprite"));
        QCOMPARE(rock["tint"].toString(), QString());
        for (const QVariant& r : rows)
            if (r.toMap()["kind"] == "sprite") QVERIFY(r.toMap()["sprite"].toString().endsWith("-night"));
    }

    void noStyleOnlyAis() {
        const QVariantList cats = legendCategories("nav", {}, "day", {});
        QCOMPARE(ids(cats), QStringList({"ais", "navaids", "lights", "hazards", "depths", "seabed"}));
        for (const QVariant& c : cats) {
            const QVariantMap m = c.toMap();
            if (m["id"] == "ais") {
                QCOMPARE(m["rows"].toList().size(), 4);
                QCOMPARE(m["needsPack"].toBool(), false);
            } else {
                QVERIFY(m["rows"].toList().isEmpty());
                QCOMPARE(m["needsPack"].toBool(), true);
            }
        }
        const QVariantList ais = category(cats, "ais")["rows"].toList();
        QCOMPARE(ais[0].toMap()["kind"].toString(), QStringLiteral("overlay"));
        QCOMPARE(ais[0].toMap()["sprite"].toString(), QStringLiteral("cm-ais-a"));
    }

    // The nav bands name the settings; the fish bands carry meters read from the band-fill stops.
    void depthBands() {
        const QVariantList nav = category(legendCategories("nav", fixture("nav-day"), "day", kSeabed), "depths")["rows"]
                                     .toList();
        const QVariantMap vs = rowLabelled(nav, "Very shallow"), deep = rowLabelled(nav, "Deep");
        QCOMPARE(vs["depthFrom"].toString(), QStringLiteral("0"));
        QCOMPARE(vs["depthTo"].toString(), QStringLiteral("shallow"));
        QCOMPARE(vs["color"].toString(), QStringLiteral("#8ec3e6"));
        QCOMPARE(deep["depthFrom"].toString(), QStringLiteral("deep"));
        QCOMPARE(deep["depthTo"].toString(), QString());

        const QVariantList fish =
            category(legendCategories("fish", fixture("fish-day"), "day", kSeabed), "depths")["rows"].toList();
        QStringList from, to, colors;
        for (const QVariant& r : fish)
            if (r.toMap()["layers"].toList() == QVariantList{"band-fill"}) {
                from << r.toMap()["depthFrom"].toString();
                to << r.toMap()["depthTo"].toString();
                colors << r.toMap()["color"].toString();
            }
        QCOMPARE(colors, QStringList({"#8ec3e6", "#b8dcf2", "#dceef9", "#f4eee2"}));
        QCOMPARE(from.size(), 4);
        QCOMPARE(from[0], QStringLiteral("0"));
        QCOMPARE(from[1].toDouble(), 9.144);
        QCOMPARE(to[0].toDouble(), 9.144);
        QCOMPARE(from[2].toDouble(), 27.432);
        QCOMPARE(from[3].toDouble(), 54.864);
        QCOMPARE(to[3], QString());
    }

    void rowFieldsFromTheStyle() {
        const QVariantList rows = allRows(legendCategories("nav", fixture("nav-day"), "day", kSeabed));
        const QVariantMap tick = rowLabelled(rows, "Restricted area ticks");
        QCOMPARE(tick["sprite"].toString(), QStringLiteral("resare-tick"));
        QCOMPARE(tick["iconSize"].toDouble(), 0.8);
        QCOMPARE(tick["tint"].toString(), QStringLiteral("#c800c8"));
        const QVariantMap cable = rowLabelled(rows, "Cable or pipeline");
        QCOMPARE(cable["kind"].toString(), QStringLiteral("line"));
        QCOMPARE(cable["dash"].toList(), (QVariantList{4.0, 2.0}));
        QCOMPARE(cable["width"].toDouble(), 1.0);
        const QVariantMap anchorage = rowLabelled(rows, "Anchorage area");
        QCOMPARE(anchorage["color"].toString(), QStringLiteral("#408e6a00")); // 0.25 opacity
        const QVariantMap sand = rowLabelled(rows, "sand");
        QCOMPARE(sand["kind"].toString(), QStringLiteral("seabed"));
        QCOMPARE(sand["text"].toString(), QStringLiteral("S"));
        QCOMPARE(rowLabelled(rows, "Rock")["iconSize"].toDouble(), 1.0);
    }
};

QTEST_GUILESS_MAIN(TstLegend)
#include "tst_legend.moc"
