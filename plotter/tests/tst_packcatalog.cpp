#include "core/PackCatalog.h"
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRandomGenerator>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>

namespace {

struct Opts {
    int schema = 1;
    QString manifestVersion;     // empty: same as the version
    bool manifest = true;
    bool mbtiles = true;
    bool styles = true;
    bool metadata = true;        // write the metadata table
    bool zoomMeta = true;        // minzoom and maxzoom rows
    bool garbageMbtiles = false; // enc.mbtiles is not SQLite
    bool valdcoJunk = false;     // valdco is not a JSON array
};

void touch(const QString& path, const QByteArray& data = {}) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile f(path);
    QVERIFY(f.open(QIODevice::WriteOnly));
    f.write(data);
}

void makeMbtiles(const QString& path, const Opts& o) {
    if (o.garbageMbtiles) {
        touch(path, "this is not an sqlite database, just some text padding it out well past a header");
        return;
    }
    const QString name = QStringLiteral("mk-") + QString::number(QRandomGenerator::global()->generate());
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), name);
        db.setDatabaseName(path);
        QVERIFY(db.open());
        QSqlQuery q(db);
        if (o.metadata) {
            QVERIFY(q.exec("CREATE TABLE metadata (name TEXT, value TEXT)"));
            q.prepare("INSERT INTO metadata VALUES (?, ?)");
            auto put = [&](const char* k, const QString& v) {
                q.addBindValue(QString::fromLatin1(k));
                q.addBindValue(v);
                QVERIFY(q.exec());
            };
            put("cheekymarine:valdco", o.valdcoJunk ? QStringLiteral("not json")
                                                    : QStringLiteral("[\"5\",\"0\",\"0.9\",\"1.8\",\"3.6\"]"));
            if (o.zoomMeta) {
                put("minzoom", QStringLiteral("6"));
                put("maxzoom", QStringLiteral("16"));
            }
        } else {
            QVERIFY(q.exec("CREATE TABLE other (x)"));
        }
    }
    QSqlDatabase::removeDatabase(name);
}

void makePack(const QString& root, const QString& kind, const QString& region, const QString& version,
              const Opts& o = {}) {
    const QString dir = root + "/" + kind + "-" + region + "-" + version;
    QVERIFY(QDir().mkpath(dir));
    if (o.manifest) {
        QJsonObject m{{"pack", kind}, {"region", region},
                      {"version", o.manifestVersion.isEmpty() ? version : o.manifestVersion},
                      {"schema", o.schema}, {"notice", "Notice for " + kind}};
        touch(dir + "/manifest.json", QJsonDocument(m).toJson());
    }
    if (o.styles)
        touch(dir + (kind == "charts" ? "/styles/nav-day.json" : "/styles/fish-day.json"), "{}");
    if (o.mbtiles) {
        if (kind == "charts") {
            makeMbtiles(dir + "/enc.mbtiles", o);
        } else {
            makeMbtiles(dir + "/bathy.mbtiles", o);
            makeMbtiles(dir + "/dem.mbtiles", o);
        }
    }
}

const PackInfo* find(const QList<PackInfo>& l, const QString& kind, const QString& ver) {
    for (const PackInfo& p : l)
        if (p.kind == kind && p.version == QVersionNumber::fromString(ver))
            return &p;
    return nullptr;
}

} // namespace

class TstPackCatalog : public QObject {
    Q_OBJECT
private slots:
    void onePack() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].kind, QString("charts"));
        QCOMPARE(l[0].region, QString("puget-north"));
        QCOMPARE(l[0].version, QVersionNumber(1, 0, 0));
        QCOMPARE(l[0].notice, QString("Notice for charts"));
        QVERIFY(l[0].refused.isEmpty());
        QCOMPARE(l[0].valdco, (QList<double>{0, 0.9, 1.8, 3.6, 5}));
        QCOMPARE(l[0].minZoom, 6);
        QCOMPARE(l[0].maxZoom, 16);
        QVERIFY(QFileInfo(l[0].dir).isDir());
    }
    void zoomAbsent() {
        QTemporaryDir t;
        Opts o;
        o.zoomMeta = false;
        makePack(t.path(), "charts", "puget-north", "1.0.0", o);
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(l.size(), 1);
        QVERIFY(l[0].refused.isEmpty());
        QCOMPARE(l[0].minZoom, -1);
        QCOMPARE(l[0].maxZoom, -1);
    }
    void bathyHasNoValdcoOrZoom() {
        QTemporaryDir t;
        makePack(t.path(), "bathy", "puget-north", "1.0.0");
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(l.size(), 1);
        QVERIFY(l[0].refused.isEmpty());
        QVERIFY(l[0].valdco.isEmpty());
        QCOMPARE(l[0].minZoom, -1);
        QCOMPARE(l[0].maxZoom, -1);
    }
    void bestIsHighestVersion() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        makePack(t.path(), "charts", "puget-north", "1.2.0");
        makePack(t.path(), "charts", "puget-north", "1.10.0");
        const auto l = PackCatalog::scan(t.path());
        const auto b = PackCatalog::best(l, u"charts");
        QVERIFY(b);
        QCOMPARE(b->version, QVersionNumber(1, 10, 0));
    }
    void bestFiltersRegion() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        makePack(t.path(), "charts", "san-juan", "2.0.0");
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(PackCatalog::best(l, u"charts")->region, QString("san-juan"));
        QCOMPARE(PackCatalog::best(l, u"charts", u"puget-north")->version, QVersionNumber(1, 0, 0));
        QVERIFY(!PackCatalog::best(l, u"charts", u"nowhere"));
    }
    void schemaTwoRefusedAndSkipped() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        Opts o;
        o.schema = 2;
        makePack(t.path(), "charts", "puget-north", "1.2.0", o);
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(find(l, "charts", "1.2.0")->refused, QString("schema 2 not supported"));
        QCOMPARE(PackCatalog::best(l, u"charts")->version, QVersionNumber(1, 0, 0));
    }
    void dirNameDisagreesWithManifest() {
        QTemporaryDir t;
        Opts o;
        o.manifestVersion = "1.0.0";
        makePack(t.path(), "charts", "puget-north", "1.1.0", o);
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].refused, QString("name does not match manifest"));
        QVERIFY(!PackCatalog::best(l, u"charts"));
    }
    void missingEncMbtiles() {
        QTemporaryDir t;
        Opts o;
        o.mbtiles = false;
        makePack(t.path(), "charts", "puget-north", "1.1.0", o);
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(find(l, "charts", "1.1.0")->refused, QString("missing enc.mbtiles"));
        QCOMPARE(PackCatalog::best(l, u"charts")->version, QVersionNumber(1, 0, 0));
    }
    void missingBathyFiles() {
        QTemporaryDir t;
        makePack(t.path(), "bathy", "puget-north", "1.0.0");
        QVERIFY(QFile::remove(t.path() + "/bathy-puget-north-1.0.0/dem.mbtiles"));
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("missing dem.mbtiles"));
        QVERIFY(QFile::remove(t.path() + "/bathy-puget-north-1.0.0/bathy.mbtiles"));
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("missing bathy.mbtiles"));
    }
    void missingManifest() {
        QTemporaryDir t;
        Opts o;
        o.manifest = false;
        makePack(t.path(), "charts", "puget-north", "1.0.0", o);
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(l.size(), 1);
        QCOMPARE(l[0].refused, QString("no manifest.json"));
    }
    void unreadableManifest() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        touch(t.path() + "/charts-puget-north-1.0.0/manifest.json", "{ not json");
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("manifest unreadable"));
        touch(t.path() + "/charts-puget-north-1.0.0/manifest.json", "[1,2]");
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("manifest unreadable"));
    }
    void stylesMissing() {
        QTemporaryDir t;
        Opts o;
        o.styles = false;
        makePack(t.path(), "charts", "puget-north", "1.0.0", o);
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("styles missing"));
    }
    void corruptMbtilesNotSqlite() {
        QTemporaryDir t;
        Opts o;
        o.garbageMbtiles = true;
        makePack(t.path(), "charts", "puget-north", "1.1.0", o);
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        const auto l = PackCatalog::scan(t.path());
        QCOMPARE(find(l, "charts", "1.1.0")->refused, QString("enc.mbtiles unreadable"));
        QCOMPARE(PackCatalog::best(l, u"charts")->version, QVersionNumber(1, 0, 0));
    }
    void corruptMbtilesNoMetadataTable() {
        QTemporaryDir t;
        Opts o;
        o.metadata = false;
        makePack(t.path(), "charts", "puget-north", "1.0.0", o);
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("enc.mbtiles unreadable"));
    }
    void valdcoNotAnArray() {
        QTemporaryDir t;
        Opts o;
        o.valdcoJunk = true;
        makePack(t.path(), "charts", "puget-north", "1.0.0", o);
        QCOMPARE(PackCatalog::scan(t.path())[0].refused, QString("enc.mbtiles unreadable"));
    }
    void strayEntriesIgnored() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        touch(t.path() + "/notes.txt", "hi");
        QDir().mkpath(t.path() + "/other-dir");
        QDir().mkpath(t.path() + "/charts-Bad_Region-1.0.0");
        QDir().mkpath(t.path() + "/charts-puget-north-1.0");
        touch(t.path() + "/charts-file-1.0.0", "a file, not a dir");
        QCOMPARE(PackCatalog::scan(t.path()).size(), 1);
    }
    void missingPacksDir() {
        QVERIFY(PackCatalog::scan("/nonexistent/packs/dir").isEmpty());
    }
    void bestEmptyKind() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        QVERIFY(!PackCatalog::best(PackCatalog::scan(t.path()), u"bathy"));
    }
    void noLeakedConnections() {
        QTemporaryDir t;
        makePack(t.path(), "charts", "puget-north", "1.0.0");
        PackCatalog::scan(t.path());
        QVERIFY(QSqlDatabase::connectionNames().isEmpty());
    }
    void realPacks() {
        const QString dir = qEnvironmentVariable("CM_PACKS_DIR");
        if (dir.isEmpty())
            QSKIP("CM_PACKS_DIR not set");
        const auto l = PackCatalog::scan(dir);
        for (const char* kind : {"charts", "bathy"}) {
            const PackInfo* p = find(l, kind, "1.0.0");
            QVERIFY2(p, kind);
            QCOMPARE(p->region, QString("puget-north"));
            QVERIFY2(p->refused.isEmpty(), qPrintable(p->refused));
        }
        const PackInfo* c = find(l, "charts", "1.0.0");
        QVERIFY(!c->valdco.isEmpty());
        QCOMPARE(c->minZoom, 6);
        QCOMPARE(c->maxZoom, 16);
    }
};

QTEST_MAIN(TstPackCatalog)
#include "tst_packcatalog.moc"
