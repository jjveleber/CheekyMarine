#include "core/StyleLoader.h"
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
}

class TstStyleLoader : public QObject {
    Q_OBJECT
private slots:
    void tileUrlForms() {
        QCOMPARE(tileUrl("/a/enc.mbtiles").value(), QStringLiteral("mbtiles:///a/enc.mbtiles"));
        QVERIFY(!tileUrl("rel/enc.mbtiles").has_value());
        QVERIFY(!tileUrl("/a?b/enc.mbtiles").has_value());
        QVERIFY(!tileUrl("/a%20b/enc.mbtiles").has_value());
    }

    void rewriteAllSixStyles_data() {
        QTest::addColumn<QString>("name");
        QTest::addColumn<bool>("fish");
        for (const char* n : {"nav-day", "nav-dusk", "nav-night"}) QTest::newRow(n) << QString(n) << false;
        for (const char* n : {"fish-day", "fish-dusk", "fish-night"}) QTest::newRow(n) << QString(n) << true;
    }
    void rewriteAllSixStyles() {
        QFETCH(QString, name);
        QFETCH(bool, fish);
        const QJsonObject in = load(name);
        QVERIFY(!in.isEmpty());
        const QString packDir = fish ? "/p/bathy" : "/p/charts";
        auto r = rewriteStyle(in, packDir, "/p/charts", "/p/bathy");
        QVERIFY2(r.has_value(), errText(r).constData());
        const QJsonObject out = *r;
        const QJsonObject src = out["sources"].toObject();
        QCOMPARE(src["enc"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/charts/enc.mbtiles"));
        if (fish) {
            QCOMPARE(src["bathy"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/bathy.mbtiles"));
            QCOMPARE(src["dem"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/dem.mbtiles"));
            QCOMPARE(out["sprite"].toString(), QStringLiteral("file:///p/bathy/sprites/fish"));
            QCOMPARE(out["glyphs"].toString(), QStringLiteral("file:///p/bathy/glyphs/{fontstack}/{range}.pbf"));
        } else {
            QCOMPARE(src.size(), 1);
            QCOMPARE(out["sprite"].toString(), QStringLiteral("file:///p/charts/sprites/nav"));
            QCOMPARE(out["glyphs"].toString(), QStringLiteral("file:///p/charts/glyphs/{fontstack}/{range}.pbf"));
        }
        QCOMPARE(QJsonDocument(out["layers"].toArray()).toJson(), QJsonDocument(in["layers"].toArray()).toJson());

        // Everything else is identical: put the rewritten keys back on a copy and compare whole objects.
        QJsonObject restored = out;
        restored["sprite"] = in["sprite"];
        restored["glyphs"] = in["glyphs"];
        restored["sources"] = in["sources"];
        QCOMPARE(restored, in);
        // Each source keeps every key but url.
        const QJsonObject inSources = in["sources"].toObject();
        QCOMPARE(src.keys(), inSources.keys());
        for (const QString& k : inSources.keys()) {
            QJsonObject a = src[k].toObject(), b = inSources[k].toObject();
            a.remove("url");
            b.remove("url");
            QCOMPARE(a, b);
        }
    }

    void rejectsForeignUrl() {
        QJsonObject s = load("nav-day");
        QJsonObject sources = s["sources"].toObject();
        QJsonObject enc = sources["enc"].toObject();
        enc["url"] = "https://x";
        sources["enc"] = enc;
        s["sources"] = sources;
        QVERIFY(!rewriteStyle(s, "/p/charts", "/p/charts", "/p/bathy").has_value());
    }
    void rejectsMismatchedAndUnknownSources() {
        QJsonObject s = load("nav-day");
        QJsonObject sources = s["sources"].toObject();
        QJsonObject enc = sources["enc"].toObject();
        enc["url"] = "mbtiles://bathy";
        sources["enc"] = enc;
        s["sources"] = sources;
        QVERIFY(!rewriteStyle(s, "/p/charts", "/p/charts", "/p/bathy").has_value());

        s = load("nav-day");
        sources = s["sources"].toObject();
        sources["other"] = sources["enc"];
        s["sources"] = sources;
        QVERIFY(!rewriteStyle(s, "/p/charts", "/p/charts", "/p/bathy").has_value());
    }
    void rejectsOddPackValues() {
        QJsonObject s = load("nav-day");
        s["sprite"] = "pack://glyphs/nav";
        QVERIFY(!rewriteStyle(s, "/p/charts", "/p/charts", "/p/bathy").has_value());
        s = load("nav-day");
        s["glyphs"] = "pack://glyphs/other";
        QVERIFY(!rewriteStyle(s, "/p/charts", "/p/charts", "/p/bathy").has_value());
    }
    void badChartsDirErrors() {
        for (const char* d : {"rel", "/a?b", "/a%20b"})
            QVERIFY(!rewriteStyle(load("nav-day"), "/p/charts", d, "/p/bathy").has_value());
    }
};

QTEST_APPLESS_MAIN(TstStyleLoader)
#include "tst_styleloader.moc"
