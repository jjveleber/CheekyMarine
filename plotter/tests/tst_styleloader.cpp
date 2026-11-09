#include "core/StyleLoader.h"
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QtTest>

namespace {
// QVERIFY2 evaluates its message eagerly, and expected::error() on a value is undefined.
template <class R> QByteArray errText(const R& r) { return r.has_value() ? QByteArray() : r.error().toLocal8Bit(); }
// Source files as the app gives them: enc from /p/charts, the four bathy sources from /p/bathy.
// An empty `bathy` leaves the bathy sources out, an empty `charts` leaves enc out.
QHash<QString, QString> files(const QString& charts = "/p/charts", const QString& bathy = "/p/bathy") {
    QHash<QString, QString> f;
    if (!charts.isEmpty()) f["enc"] = charts + "/enc.mbtiles";
    if (!bathy.isEmpty())
        for (const char* n : {"bathy", "dem", "bathy-coarse", "dem-coarse"}) f[n] = bathy + "/" + n + ".mbtiles";
    return f;
}
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
        auto r = rewriteStyle(in, packDir, files());
        QVERIFY2(r.has_value(), errText(r).constData());
        const QJsonObject out = *r;
        const QJsonObject src = out["sources"].toObject();
        QCOMPARE(src["enc"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/charts/enc.mbtiles"));
        if (fish) {
            QCOMPARE(src["bathy"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/bathy.mbtiles"));
            QCOMPARE(src["dem"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/dem.mbtiles"));
            QCOMPARE(src["bathy-coarse"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/bathy-coarse.mbtiles"));
            QCOMPARE(src["dem-coarse"].toObject()["url"].toString(), QStringLiteral("mbtiles:///p/bathy/dem-coarse.mbtiles"));
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
        QVERIFY(!rewriteStyle(s, "/p/charts", files()).has_value());
    }
    void rejectsMismatchedSourceUrl() {
        QJsonObject s = load("nav-day");
        QJsonObject sources = s["sources"].toObject();
        QJsonObject enc = sources["enc"].toObject();
        enc["url"] = "mbtiles://bathy";
        sources["enc"] = enc;
        s["sources"] = sources;
        QVERIFY(!rewriteStyle(s, "/p/charts", files()).has_value());
    }
    void unknownSourceIsError() {
        QJsonObject s = load("nav-day");
        QJsonObject sources = s["sources"].toObject();
        sources["fooo"] = sources["enc"];
        s["sources"] = sources;
        auto r = rewriteStyle(s, "/p/charts", files());
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), QStringLiteral("unknown source: fooo"));
    }
    void rejectsOddPackValues() {
        QJsonObject s = load("nav-day");
        s["sprite"] = "pack://glyphs/nav";
        QVERIFY(!rewriteStyle(s, "/p/charts", files()).has_value());
        s = load("nav-day");
        s["glyphs"] = "pack://glyphs/other";
        QVERIFY(!rewriteStyle(s, "/p/charts", files()).has_value());
    }
    void rewritesCoarseSources() {
        QJsonObject s = load("fish-day");
        auto r = rewriteStyle(s, "/p/bathy", files());
        QVERIFY2(r.has_value(), errText(r).constData());
        QCOMPARE(r->value("sources").toObject()["bathy-coarse"].toObject()["url"].toString(),
                 QStringLiteral("mbtiles:///p/bathy/bathy-coarse.mbtiles"));
    }
    void missingSourceFileIsError() {
        QHash<QString, QString> f = files();
        f.remove("dem-coarse");
        auto r = rewriteStyle(load("fish-day"), "/p/bathy", f);
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), QStringLiteral("source dem-coarse needs a pack that is not there"));
    }
    void noSpritePassesThrough() {
        QJsonObject s = load("nav-day");
        s.remove("sprite");
        auto r = rewriteStyle(s, "/p/charts", files());
        QVERIFY2(r.has_value(), errText(r).constData());
        QVERIFY(!r->contains("sprite"));
        QCOMPARE(r->value("glyphs").toString(), QStringLiteral("file:///p/charts/glyphs/{fontstack}/{range}.pbf"));
    }
    void noGlyphsPassesThrough() {
        QJsonObject s = load("nav-day");
        s.remove("glyphs");
        auto r = rewriteStyle(s, "/p/charts", files());
        QVERIFY2(r.has_value(), errText(r).constData());
        QVERIFY(!r->contains("glyphs"));
        QCOMPARE(r->value("sprite").toString(), QStringLiteral("file:///p/charts/sprites/nav"));
    }
    void badChartsDirErrors() {
        for (const char* d : {"rel", "/a?b", "/a%20b"})
            QVERIFY(!rewriteStyle(load("nav-day"), "/p/charts", files(d)).has_value());
    }
    // No bathy pack (empty bathyDir): a style using a bathy-pack source cannot be rewritten; one
    // using only enc can.
    void bathySourceWithoutBathyDirErrors() {
        QVERIFY(!rewriteStyle(load("fish-day"), "/p/bathy", files("/p/charts", "")).has_value());
        auto r = rewriteStyle(load("nav-day"), "/p/charts", files("/p/charts", ""));
        QVERIFY2(r.has_value(), errText(r).constData());
        QVERIFY(!rewriteStyle(load("nav-day"), "/p/charts", files("", "/p/bathy")).has_value());
    }
};

QTEST_APPLESS_MAIN(TstStyleLoader)
#include "tst_styleloader.moc"
