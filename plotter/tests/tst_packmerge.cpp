#include "core/PackCatalog.h"
#include "core/PackMerge.h"
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRandomGenerator>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>

namespace {

struct Row {
    int z, col, row; // stored (TMS) coordinates
    QByteArray data;
    QString id = {}; // tile_id in the map/images layout; empty: derived from data
};

struct Mb {
    QList<Row> rows;
    bool mapImages = false; // tile-join layout: map + images, tiles a view
    QString format = "pbf";
    QString minzoom, maxzoom, bounds, json, valdco;
};

QString meta(const QString& path, const QString& name) {
    const QString conn = "q-" + QString::number(QRandomGenerator::global()->generate());
    QString v;
    {
        QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", conn);
        db.setDatabaseName(path);
        db.setConnectOptions("QSQLITE_OPEN_READONLY");
        if (db.open()) {
            QSqlQuery q(db);
            q.prepare("SELECT value FROM metadata WHERE name = ?");
            q.addBindValue(name);
            if (q.exec() && q.next())
                v = q.value(0).toString();
        }
    }
    QSqlDatabase::removeDatabase(conn);
    return v;
}

qint64 count(const QString& path, const QString& sql) {
    const QString conn = "c-" + QString::number(QRandomGenerator::global()->generate());
    qint64 n = -1;
    {
        QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", conn);
        db.setDatabaseName(path);
        db.setConnectOptions("QSQLITE_OPEN_READONLY");
        if (db.open()) {
            QSqlQuery q(db);
            if (q.exec(sql) && q.next())
                n = q.value(0).toLongLong();
        }
    }
    QSqlDatabase::removeDatabase(conn);
    return n;
}

void writeMb(const QString& path, const Mb& m) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    const QString conn = "w-" + QString::number(QRandomGenerator::global()->generate());
    {
        QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", conn);
        db.setDatabaseName(path);
        QVERIFY(db.open());
        QSqlQuery q(db);
        QVERIFY(q.exec("CREATE TABLE metadata (name text, value text)"));
        auto put = [&](const char* k, const QString& v) {
            if (v.isEmpty())
                return;
            q.prepare("INSERT INTO metadata VALUES (?, ?)");
            q.addBindValue(QString::fromLatin1(k));
            q.addBindValue(v);
            QVERIFY(q.exec());
        };
        put("format", m.format);
        put("minzoom", m.minzoom);
        put("maxzoom", m.maxzoom);
        put("bounds", m.bounds);
        put("json", m.json);
        put("cheekymarine:valdco", m.valdco);
        if (m.mapImages) {
            QVERIFY(q.exec("CREATE TABLE map (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_id TEXT)"));
            QVERIFY(q.exec("CREATE UNIQUE INDEX map_index ON map (zoom_level, tile_column, tile_row)"));
            QVERIFY(q.exec("CREATE TABLE images (zoom_level integer, tile_data blob, tile_id text)"));
            QVERIFY(q.exec("CREATE UNIQUE INDEX images_id ON images (zoom_level, tile_id)"));
            QVERIFY(q.exec("CREATE VIEW tiles AS SELECT map.zoom_level AS zoom_level, map.tile_column AS tile_column, "
                           "map.tile_row AS tile_row, images.tile_data AS tile_data FROM map JOIN images ON "
                           "images.tile_id = map.tile_id AND images.zoom_level = map.zoom_level"));
            for (const Row& r : m.rows) {
                const QString id = r.id.isEmpty() ? QString::fromLatin1(QCryptographicHash::hash(r.data, QCryptographicHash::Md5).toHex()) : r.id;
                q.prepare("INSERT INTO map VALUES (?, ?, ?, ?)");
                q.addBindValue(r.z); q.addBindValue(r.col); q.addBindValue(r.row); q.addBindValue(id);
                QVERIFY(q.exec());
                q.prepare("INSERT OR IGNORE INTO images VALUES (?, ?, ?)");
                q.addBindValue(r.z); q.addBindValue(r.data); q.addBindValue(id);
                QVERIFY(q.exec());
            }
        } else {
            QVERIFY(q.exec("CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)"));
            QVERIFY(q.exec("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)"));
            for (const Row& r : m.rows) {
                q.prepare("INSERT INTO tiles VALUES (?, ?, ?, ?)");
                q.addBindValue(r.z); q.addBindValue(r.col); q.addBindValue(r.row); q.addBindValue(r.data);
                QVERIFY(q.exec());
            }
        }
    }
    QSqlDatabase::removeDatabase(conn);
}

PackInfo pack(const QString& root, const QString& kind, const QString& region, const QString& version,
              const QMap<QString, Mb>& files, int schema = PLOTTER_PACK_SCHEMA_MIN) {
    PackInfo p;
    p.kind = kind;
    p.region = region;
    p.version = QVersionNumber::fromString(version);
    p.dir = root + "/" + kind + "-" + region + "-" + version;
    QDir().mkpath(p.dir);
    QFile mf(p.dir + "/manifest.json");
    if (mf.open(QIODevice::WriteOnly))
        mf.write(QJsonDocument(QJsonObject{{"pack", kind}, {"region", region}, {"version", version},
                                           {"schema", schema}}).toJson());
    for (auto it = files.begin(); it != files.end(); ++it)
        writeMb(p.dir + "/" + it.key(), it.value());
    return p;
}

Mb mb(QList<Row> rows, const QString& minz, const QString& maxz) {
    Mb m;
    m.rows = rows;
    m.minzoom = minz;
    m.maxzoom = maxz;
    return m;
}

// All four bathy files, empty unless given.
QMap<QString, Mb> bathyFiles(const QMap<QString, Mb>& given) {
    QMap<QString, Mb> out;
    for (const QString& f : kBathyFiles)
        out[f] = given.value(f, mb({}, "", ""));
    return out;
}

} // namespace

class TstPackMerge : public QObject {
    Q_OBJECT
private slots:
    void mergesDisjointRows() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", mb({{10, 163, 357, "A"}}, "10", "10")}});
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", mb({{10, 164, 357, "B"}}, "10", "10")}});
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        const QString f = o.path() + "/charts/enc.mbtiles";
        QCOMPARE(count(f, "SELECT count(*) FROM tiles"), 2);
        QCOMPARE(meta(f, "minzoom"), QString("10"));
        QCOMPARE(meta(f, "format"), QString("pbf"));
        QCOMPARE(mergeMembers(f).size(), 2);
        QCOMPARE(mergeMembers(f)[0].dir, QString("charts-a-1.0.0"));
        QCOMPARE(mergeMembers(f)[1].dir, QString("charts-b-1.0.0"));
        QVERIFY(!QFileInfo::exists(f + ".tmp"));
        QVERIFY(QSqlDatabase::connectionNames().isEmpty());
    }
    void membersCarryManifestHash() {
        QTemporaryDir t, o;
        // b sorts before a-x by region, but members sort by dir name
        const auto a = pack(t.path(), "charts", "a-x", "1.0.0", {{"enc.mbtiles", mb({{10, 1, 1, "A"}}, "10", "10")}});
        const auto b = pack(t.path(), "charts", "a", "2.0.0", {{"enc.mbtiles", mb({{10, 2, 2, "B"}}, "10", "10")}});
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        auto sha = [](const PackInfo& p) {
            QFile f(p.dir + "/manifest.json");
            return f.open(QIODevice::ReadOnly) ? QString::fromLatin1(QCryptographicHash::hash(f.readAll(), QCryptographicHash::Sha256).toHex())
                                               : QString();
        };
        const QString f = o.path() + "/charts/enc.mbtiles";
        QCOMPARE(QJsonDocument::fromJson(meta(f, "cheekymarine:members").toUtf8()).array(),
                 (QJsonArray{QJsonObject{{"dir", "charts-a-2.0.0"}, {"manifest_sha256", sha(b)}},
                             QJsonObject{{"dir", "charts-a-x-1.0.0"}, {"manifest_sha256", sha(a)}}}));
        QCOMPARE(mergeMembers(f), (QList<MergeMember>{{"charts-a-2.0.0", sha(b)}, {"charts-a-x-1.0.0", sha(a)}}));
        QCOMPARE(manifestSha256(a.dir), sha(a));
        QVERIFY(sha(a) != sha(b));
    }
    void mergedFileCarriesSchema() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "bathy", "a", "1.0.0", bathyFiles({{"bathy.mbtiles", mb({{9, 1, 1, "x"}}, "9", "9")}}));
        const auto b = pack(t.path(), "bathy", "b", "1.0.0", bathyFiles({{"bathy.mbtiles", mb({{9, 2, 2, "y"}}, "9", "9")}}));
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        for (const QString& f : kBathyFiles) {
            QCOMPARE(meta(o.path() + "/bathy/" + f, "cheekymarine:schema"), QString::number(PLOTTER_PACK_SCHEMA_MIN));
            QCOMPARE(mergeSchema(o.path() + "/bathy/" + f), std::optional<int>(PLOTTER_PACK_SCHEMA_MIN));
        }
    }
    void memberSchemasMustAgree() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", mb({{10, 1, 1, "A"}}, "10", "10")}}, 2);
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", mb({{10, 2, 2, "B"}}, "10", "10")}}, 3);
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), QString("schema differs: charts-a-1.0.0 2, charts-b-1.0.0 3"));
        QVERIFY(QDir(o.path() + "/charts").entryList({"*.mbtiles", "*.tmp"}, QDir::Files).isEmpty());
    }
    void mergedFileCarriesLegend() {
        QTemporaryDir t, o;
        auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", mb({{10, 1, 1, "A"}}, "10", "10")}});
        auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", mb({{10, 2, 2, "B"}}, "10", "10")}});
        a.legend = {{"Blds", "boulders", "type"}, {"Sand", "sand", "type"}};
        b.legend = {{"Blds", "boulders again", "type"}, {"Blds", "boulders", "kind2"}};
        const auto r = mergePacks({b, a}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        const QString f = o.path() + "/charts/enc.mbtiles";
        // first wins per abbr and kind, members in region order
        QCOMPARE(QJsonDocument::fromJson(meta(f, "cheekymarine:legend").toUtf8()).array(),
                 (QJsonArray{QJsonObject{{"abbr", "Blds"}, {"meaning", "boulders"}, {"kind", "type"}},
                             QJsonObject{{"abbr", "Sand"}, {"meaning", "sand"}, {"kind", "type"}},
                             QJsonObject{{"abbr", "Blds"}, {"meaning", "boulders"}, {"kind", "kind2"}}}));
        const QList<LegendEntry> l = mergeLegend(f);
        QCOMPARE(l.size(), 3);
        QCOMPARE(l[2].kind, QString("kind2"));
    }
    void unreadableManifestFails() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", mb({{10, 1, 1, "A"}}, "10", "10")}});
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", mb({{10, 2, 2, "B"}}, "10", "10")}});
        QVERIFY(QFile::remove(b.dir + "/manifest.json"));
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), QString("charts-b-1.0.0: cannot read manifest.json"));
        QVERIFY(QDir(o.path() + "/charts").entryList({"*.mbtiles", "*.tmp"}, QDir::Files).isEmpty());
    }
    void oldMembersFormatIsNotValid() {
        QTemporaryDir t;
        Mb m = mb({}, "", "");
        writeMb(t.path() + "/enc.mbtiles", m);
        const QString conn = "old-members";
        {
            QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", conn);
            db.setDatabaseName(t.path() + "/enc.mbtiles");
            QVERIFY(db.open());
            QSqlQuery q(db);
            QVERIFY(q.exec(R"(INSERT INTO metadata VALUES ('cheekymarine:members', '["charts-a-1.0.0","charts-b-1.0.0"]'))"));
        }
        QSqlDatabase::removeDatabase(conn);
        QVERIFY(mergeMembers(t.path() + "/enc.mbtiles").isEmpty());
        QCOMPARE(mergeSchema(t.path() + "/enc.mbtiles"), std::optional<int>());
    }
    void plainTilesMerge() {
        QTemporaryDir t, o;
        Mb x = mb({{9, 1, 1, "x"}}, "9", "9"), y = mb({{9, 2, 2, "y"}}, "9", "9");
        const auto a = pack(t.path(), "bathy", "a", "1.0.0", bathyFiles({{"bathy.mbtiles", x}}));
        const auto b = pack(t.path(), "bathy", "b", "1.0.0", bathyFiles({{"bathy.mbtiles", y}}));
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        for (const QString& f : kBathyFiles)
            QVERIFY(QFileInfo::exists(o.path() + "/bathy/" + f));
        QCOMPARE(count(o.path() + "/bathy/bathy.mbtiles", "SELECT count(*) FROM tiles WHERE tile_data IN (x'78', x'79')"), 2);
    }
    void unitesMetadata() {
        QTemporaryDir t, o;
        Mb x = mb({{6, 1, 1, "x"}}, "6", "9"), y = mb({{16, 2, 2, "y"}}, "10", "16");
        x.valdco = "[5,10]";
        y.valdco = "[10,20]";
        x.json = R"({"vector_layers":[{"id":"depare","fields":{}}]})";
        y.json = R"({"vector_layers":[{"id":"depare","fields":{"z":"n"}},{"id":"soundg","fields":{}}]})";
        x.bounds = "-123,47,-122,48";
        y.bounds = "-122.5,47.5,-121,49";
        x.mapImages = y.mapImages = true;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", x}});
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", y}});
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        const QString f = o.path() + "/charts/enc.mbtiles";
        QCOMPARE(meta(f, "minzoom"), QString("6"));
        QCOMPARE(meta(f, "maxzoom"), QString("16"));
        QCOMPARE(meta(f, "bounds"), QString("-123,47,-121,49"));
        QCOMPARE(QJsonDocument::fromJson(meta(f, "cheekymarine:valdco").toUtf8()).array(),
                 (QJsonArray{5, 10, 20}));
        QCOMPARE(mergeValdco(f), (QList<double>{5, 10, 20}));
        const QJsonArray layers = QJsonDocument::fromJson(meta(f, "json").toUtf8()).object()["vector_layers"].toArray();
        QCOMPARE(layers.size(), 2);
        QCOMPARE(layers[0].toObject()["id"].toString(), QString("depare"));
        QVERIFY(layers[0].toObject()["fields"].toObject().isEmpty()); // first wins
    }
    void duplicateTileFailsAndLeavesNothing() {
        QTemporaryDir t, o;
        Mb x = mb({{10, 163, 357, "A"}}, "10", "10"), y = mb({{10, 163, 357, "B"}}, "10", "10");
        x.mapImages = y.mapImages = true; // the map layout fails the same way
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", x}});
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", y}});
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        // stored row 357 at zoom 10 is XYZ y 1023 - 357 = 666
        QCOMPARE(r.error(), QString("tile 10/163/666 is in both charts-a-1.0.0 and charts-b-1.0.0"));
        QVERIFY(QDir(o.path() + "/charts").entryList({"*.mbtiles", "*.tmp"}, QDir::Files).isEmpty());
        QVERIFY(QSqlDatabase::connectionNames().isEmpty());
    }
    void duplicateTileInPlainBathyFails() {
        QTemporaryDir t, o;
        // bathy.mbtiles is disjoint and merges first; the duplicate is in dem.mbtiles, the second file, so
        // the cleanup of the finished bathy.mbtiles.tmp is covered too. Plain tiles tables, no map/images.
        const auto a = pack(t.path(), "bathy", "a", "1.0.0",
                            bathyFiles({{"bathy.mbtiles", mb({{10, 1, 1, "x"}}, "10", "10")},
                                        {"dem.mbtiles", mb({{10, 163, 357, "p"}}, "10", "10")}}));
        const auto b = pack(t.path(), "bathy", "b", "1.0.0",
                            bathyFiles({{"bathy.mbtiles", mb({{10, 2, 2, "y"}}, "10", "10")},
                                        {"dem.mbtiles", mb({{10, 163, 357, "q"}}, "10", "10")}}));
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        // stored row 357 at zoom 10 is XYZ y 1023 - 357 = 666
        QCOMPARE(r.error(), QString("tile 10/163/666 is in both bathy-a-1.0.0 and bathy-b-1.0.0"));
        QVERIFY(QDir(o.path() + "/bathy").entryList(QDir::Files | QDir::NoDotAndDotDot).isEmpty());
        QVERIFY(QSqlDatabase::connectionNames().isEmpty());
    }
    void memberWithNoTilesKeepsOthersZooms() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "bathy", "overview", "1.0.0",
                            bathyFiles({{"bathy.mbtiles", mb({{5, 1, 1, "o"}}, "5", "5")}}));
        // empty fine files claim minzoom 0
        Mb empty = mb({}, "0", "16");
        const auto b = pack(t.path(), "bathy", "b", "1.0.0",
                            [&] { auto m = bathyFiles({{"bathy.mbtiles", mb({{12, 1, 1, "f"}}, "11", "12")}}); m["dem.mbtiles"] = empty; return m; }());
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        QCOMPARE(meta(o.path() + "/bathy/dem.mbtiles", "minzoom"), QString());
        QCOMPARE(meta(o.path() + "/bathy/bathy.mbtiles", "minzoom"), QString("5"));
        // the fine file with only b's tiles keeps b's zooms: a has none there
        const auto c = pack(t.path(), "bathy", "c", "1.0.0", bathyFiles({{"bathy.mbtiles", mb({{12, 3, 3, "g"}}, "12", "12")}}));
        const auto r2 = mergePacks({b, c}, o.path());
        QVERIFY2(r2.has_value(), qPrintable(r2.error()));
        QCOMPARE(meta(o.path() + "/bathy/bathy.mbtiles", "minzoom"), QString("11"));
    }
    void singlePackKindIsNotMerged() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", mb({{10, 1, 1, "A"}}, "10", "10")}});
        const auto r = mergePacks({a}, o.path());
        QVERIFY(r.has_value());
        QVERIFY(!QFileInfo::exists(o.path() + "/charts"));
    }
    void regionMaxzoomMismatchFails() {
        QTemporaryDir t, o;
        auto mk = [&](const QString& region, const QString& maxz, int z) {
            return pack(t.path(), "bathy", region, "1.0.0",
                        bathyFiles({{"bathy-coarse.mbtiles", mb({{z, 1, 1, region.toUtf8()}}, QString::number(z), maxz)}}));
        };
        const auto a = mk("a", "12", 12), b = mk("b", "11", 11);
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        QCOMPARE(r.error(), QString("bathy-coarse.mbtiles: maxzoom differs: bathy-a-1.0.0 12, bathy-b-1.0.0 11"));
        QVERIFY(QDir(o.path() + "/bathy").entryList({"*.mbtiles", "*.tmp"}, QDir::Files).isEmpty());
        // an overview member below zoom 10 is exempt
        const auto c = mk("c", "9", 9);
        const auto r2 = mergePacks({a, c}, o.path());
        QVERIFY2(r2.has_value(), qPrintable(r2.error()));
        QCOMPARE(meta(o.path() + "/bathy/bathy-coarse.mbtiles", "maxzoom"), QString("12"));
    }
    void missingFileNamesPackAndFile() {
        QTemporaryDir t, o;
        const auto a = pack(t.path(), "bathy", "a", "1.0.0", bathyFiles({}));
        auto files = bathyFiles({});
        files.remove("dem-coarse.mbtiles");
        const auto b = pack(t.path(), "bathy", "b", "1.0.0", files);
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY(!r.has_value());
        QVERIFY2(r.error().contains("bathy-b-1.0.0") && r.error().contains("dem-coarse.mbtiles"), qPrintable(r.error()));
        QVERIFY(QDir(o.path() + "/bathy").entryList({"*.mbtiles", "*.tmp"}, QDir::Files).isEmpty());
    }
    void keepsTileDedup() {
        QTemporaryDir t, o;
        Mb x = mb({{10, 1, 1, "same"}}, "10", "10"), y = mb({{10, 2, 2, "same"}}, "10", "10");
        x.rows[0].data = y.rows[0].data = "shared tile bytes";
        x.mapImages = y.mapImages = true;
        const auto a = pack(t.path(), "charts", "a", "1.0.0", {{"enc.mbtiles", x}});
        const auto b = pack(t.path(), "charts", "b", "1.0.0", {{"enc.mbtiles", y}});
        const auto r = mergePacks({a, b}, o.path());
        QVERIFY2(r.has_value(), qPrintable(r.error()));
        const QString f = o.path() + "/charts/enc.mbtiles";
        QCOMPARE(count(f, "SELECT count(*) FROM images"), 1);
        QCOMPARE(count(f, "SELECT count(*) FROM map"), 2);
        QCOMPARE(count(f, "SELECT count(*) FROM tiles"), 2);
        QCOMPARE(count(f, "SELECT count(*) FROM sqlite_master WHERE name = 'tiles' AND type = 'view'"), 1);
    }
    void usableTakesNewestPerRegion() {
        auto mk = [](const QString& region, const char* v) {
            PackInfo p;
            p.kind = "charts";
            p.region = region;
            p.version = QVersionNumber::fromString(v);
            return p;
        };
        const auto u = PackCatalog::usable({mk("b", "1.0.0"), mk("a", "1.0.0"), mk("a", "1.1.0")}, u"charts");
        QCOMPARE(u.size(), 2);
        QCOMPARE(u[0].region, QString("a"));
        QCOMPARE(u[0].version, QVersionNumber(1, 1, 0));
        QCOMPARE(u[1].region, QString("b"));
        QCOMPARE(u[1].version, QVersionNumber(1, 0, 0));
    }
};

QTEST_MAIN(TstPackMerge)
#include "tst_packmerge.moc"
