#include "core/PackMerge.h"
#include "core/NoticeAreas.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRandomGenerator>
#include <QSet>
#include <QSqlDatabase>
#include <QSqlError>
#include <QSqlQuery>
#include <algorithm>
#include <limits>
#include <optional>

namespace {

// Zoom 10 and up is the fine range, where members must agree on maxzoom; the overview is below it.
constexpr int kFineZoom = 10;

QString unique(const char* what) {
    return QString::fromLatin1(what) + QString::number(QRandomGenerator::global()->generate64(), 16);
}

// A SQLite connection with a unique name, removed on destruction. The QSqlDatabase handle is looked up
// on demand so no copy outlives the connection.
class Conn {
public:
    Conn(const QString& path, bool readOnly) : m_name(unique("packmerge-")) {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), m_name);
        db.setDatabaseName(path);
        if (readOnly)
            db.setConnectOptions(QStringLiteral("QSQLITE_OPEN_READONLY"));
        m_ok = db.open();
        if (!m_ok)
            m_error = db.lastError().text();
    }
    ~Conn() {
        {
            QSqlDatabase db = QSqlDatabase::database(m_name, false);
            if (db.isOpen())
                db.close();
        }
        QSqlDatabase::removeDatabase(m_name);
    }
    Conn(const Conn&) = delete;
    Conn& operator=(const Conn&) = delete;
    bool ok() const { return m_ok; }
    QString error() const { return m_error; }
    QSqlDatabase db() const { return QSqlDatabase::database(m_name, false); }

private:
    QString m_name;
    bool m_ok = false;
    QString m_error;
};

// Runs `sql` with optional bindings; false with the driver's message in `err`.
bool run(QSqlDatabase db, const QString& sql, QString& err, const QVariantList& binds = {}) {
    QSqlQuery q(db);
    q.prepare(sql);
    for (const QVariant& v : binds)
        q.addBindValue(v);
    if (q.exec())
        return true;
    err = q.lastError().text();
    return false;
}

struct Member {
    PackInfo pack;
    QString name;           // pack directory name
    bool mapImages = false; // tile-join layout: map + images, `tiles` a view over them
    bool hasTiles = false;
    int minZoom = -1, maxZoom = -1;
    QString format;
    QList<double> bounds;   // w, s, e, n; empty when absent
    QJsonArray layers;      // vector_layers
    QJsonArray valdco;
    NoticeAreas noticeAreas;
    QString dataNotice;
    bool hasJson = false;
};

// The metadata and shape of one member file. nullopt with `err` set when it cannot be read.
std::optional<Member> readMember(const PackInfo& p, const QString& file, QString& err) {
    Member m;
    m.pack = p;
    m.name = QFileInfo(p.dir).fileName();
    const QString path = p.dir + QLatin1Char('/') + file;
    if (!QFileInfo::exists(path)) {
        err = m.name + QStringLiteral(": missing ") + file;
        return std::nullopt;
    }
    Conn c(path, true);
    if (!c.ok()) {
        err = m.name + QStringLiteral(": cannot open ") + file + QStringLiteral(": ") + c.error();
        return std::nullopt;
    }
    QSqlDatabase db = c.db();
    QString e;
    QSqlQuery q(db);
    if (!q.exec(QStringLiteral("SELECT name, value FROM metadata"))) {
        err = m.name + QStringLiteral(": ") + file + QStringLiteral(" has no metadata: ") + q.lastError().text();
        return std::nullopt;
    }
    int metaMin = -1, metaMax = -1;
    while (q.next()) {
        const QString k = q.value(0).toString(), v = q.value(1).toString();
        if (k == QLatin1String("format")) {
            m.format = v;
        } else if (k == QLatin1String("minzoom")) {
            metaMin = v.toInt();
        } else if (k == QLatin1String("maxzoom")) {
            metaMax = v.toInt();
        } else if (k == QLatin1String("bounds")) {
            const QStringList parts = v.split(QLatin1Char(','));
            if (parts.size() == 4)
                for (const QString& s : parts)
                    m.bounds.append(s.trimmed().toDouble());
        } else if (k == QLatin1String("json")) {
            m.hasJson = true;
            m.layers = QJsonDocument::fromJson(v.toUtf8()).object().value(QStringLiteral("vector_layers")).toArray();
        } else if (k == QLatin1String("cheekymarine:valdco")) {
            m.valdco = QJsonDocument::fromJson(v.toUtf8()).array();
        } else if (k == QLatin1String("cheekymarine:notice_areas")) {
            m.noticeAreas = NoticeAreas::fromGeoJson(v.toUtf8());
        } else if (k == QLatin1String("cheekymarine:data_notice")) {
            m.dataNotice = v;
        }
    }
    QSqlQuery t(db);
    if (!t.exec(QStringLiteral("SELECT min(zoom_level), max(zoom_level) FROM tiles")) || !t.next()) {
        err = m.name + QStringLiteral(": ") + file + QStringLiteral(" has no tiles table: ") + t.lastError().text();
        return std::nullopt;
    }
    // Zooms come from the metadata; the rows fill in when it has none. A file with no rows has no zooms.
    m.hasTiles = !t.value(0).isNull();
    if (m.hasTiles) {
        m.minZoom = metaMin >= 0 ? metaMin : t.value(0).toInt();
        m.maxZoom = metaMax >= 0 ? metaMax : t.value(1).toInt();
    }
    QSqlQuery l(db);
    l.exec(QStringLiteral("SELECT (SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'map'),"
                          " (SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'images'),"
                          " (SELECT count(*) FROM pragma_table_info('images') WHERE name = 'zoom_level')"));
    m.mapImages = l.next() && l.value(0).toInt() == 1 && l.value(1).toInt() == 1 && l.value(2).toInt() == 1;
    return m;
}

double num(const QJsonValue& v) { return v.isString() ? v.toString().toDouble() : v.toDouble(); }

// Everything that goes into the merged file's metadata table.
QList<QPair<QString, QString>> mergedMetadata(const QList<Member>& ms, bool charts, const QJsonArray& members, int schema) {
    QList<QPair<QString, QString>> out;
    out.append({QStringLiteral("format"), ms.first().format});

    int minZ = std::numeric_limits<int>::max(), maxZ = -1;
    for (const Member& m : ms)
        if (m.hasTiles) {
            minZ = std::min(minZ, m.minZoom);
            maxZ = std::max(maxZ, m.maxZoom);
        }
    if (maxZ >= 0) {
        out.append({QStringLiteral("minzoom"), QString::number(minZ)});
        out.append({QStringLiteral("maxzoom"), QString::number(maxZ)});
    }

    QList<double> b;
    for (const Member& m : ms)
        if (m.bounds.size() == 4) {
            if (b.isEmpty())
                b = m.bounds;
            else
                b = {std::min(b[0], m.bounds[0]), std::min(b[1], m.bounds[1]), std::max(b[2], m.bounds[2]),
                     std::max(b[3], m.bounds[3])};
        }
    if (!b.isEmpty())
        out.append({QStringLiteral("bounds"),
                    QStringLiteral("%1,%2,%3,%4").arg(b[0], 0, 'g', 12).arg(b[1], 0, 'g', 12).arg(b[2], 0, 'g', 12).arg(b[3], 0, 'g', 12)});

    bool anyJson = false;
    QJsonArray layers;
    QStringList seen;
    for (const Member& m : ms) {
        anyJson |= m.hasJson;
        for (const QJsonValue& l : m.layers) {
            const QString id = l.toObject().value(QStringLiteral("id")).toString();
            if (!seen.contains(id)) { // first wins
                seen.append(id);
                layers.append(l);
            }
        }
    }
    if (anyJson)
        out.append({QStringLiteral("json"), QString::fromUtf8(QJsonDocument(QJsonObject{{"vector_layers", layers}}).toJson(QJsonDocument::Compact))});

    if (charts) {
        QList<QJsonValue> vals;
        for (const Member& m : ms)
            for (const QJsonValue& v : m.valdco)
                if (std::none_of(vals.begin(), vals.end(), [&](const QJsonValue& o) { return num(o) == num(v); }))
                    vals.append(v);
        std::sort(vals.begin(), vals.end(), [](const QJsonValue& a, const QJsonValue& c) { return num(a) < num(c); });
        QJsonArray arr;
        for (const QJsonValue& v : vals)
            arr.append(v);
        out.append({QStringLiteral("cheekymarine:valdco"), QString::fromUtf8(QJsonDocument(arr).toJson(QJsonDocument::Compact))});

        // legend.json is not merged as a file: its union (first wins per abbr and kind) goes here.
        QJsonArray legend;
        QSet<QPair<QString, QString>> seenEntries;
        for (const Member& m : ms)
            for (const LegendEntry& e : m.pack.legend)
                if (!seenEntries.contains({e.abbr, e.kind})) {
                    seenEntries.insert({e.abbr, e.kind});
                    legend.append(QJsonObject{{QStringLiteral("abbr"), e.abbr}, {QStringLiteral("meaning"), e.meaning},
                                              {QStringLiteral("kind"), e.kind}});
                }
        out.append({QStringLiteral("cheekymarine:legend"), QString::fromUtf8(QJsonDocument(legend).toJson(QJsonDocument::Compact))});
    }

    NoticeAreas areas;
    QStringList dataNotices;
    for (const Member& m : ms) {
        areas.add(m.noticeAreas);
        if (!m.dataNotice.isEmpty() && !dataNotices.contains(m.dataNotice))
            dataNotices.append(m.dataNotice);
    }
    if (!areas.isEmpty())
        out.append({QStringLiteral("cheekymarine:notice_areas"), QString::fromUtf8(areas.toGeoJson())});
    if (!dataNotices.isEmpty())
        out.append({QStringLiteral("cheekymarine:data_notice"), dataNotices.join(QStringLiteral("\n\n"))});

    out.append({QStringLiteral("cheekymarine:members"),
                QString::fromUtf8(QJsonDocument(members).toJson(QJsonDocument::Compact))});
    out.append({QStringLiteral("cheekymarine:schema"), QString::number(schema)});
    return out;
}

// Does the member file hold a tile at the stored coordinates?
bool memberHasTile(const Member& m, const QString& file, int z, int col, int row) {
    Conn c(m.pack.dir + QLatin1Char('/') + file, true);
    if (!c.ok())
        return false;
    QSqlQuery q(c.db());
    q.prepare(QStringLiteral("SELECT 1 FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?"));
    q.addBindValue(z);
    q.addBindValue(col);
    q.addBindValue(row);
    return q.exec() && q.next();
}

// Writes one merged MBTiles at `tmpPath`. `err` is set on failure.
bool writeMerged(const QList<Member>& ms, const QString& file, bool charts, const QJsonArray& members, int packSchema,
                 const QString& tmpPath, QString& err) {
    // map/images only when every member has it; otherwise the rows go to a plain `tiles` table.
    const bool mapImages = std::all_of(ms.begin(), ms.end(), [](const Member& m) { return m.mapImages; });
    Conn c(tmpPath, false);
    if (!c.ok()) {
        err = QStringLiteral("cannot create ") + tmpPath + QStringLiteral(": ") + c.error();
        return false;
    }
    QSqlDatabase db = c.db();
    QStringList schema{QStringLiteral("CREATE TABLE metadata (name text, value text)"),
                       QStringLiteral("CREATE UNIQUE INDEX name ON metadata (name)")};
    if (mapImages)
        schema << QStringLiteral("CREATE TABLE map (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_id TEXT)")
               << QStringLiteral("CREATE UNIQUE INDEX map_index ON map (zoom_level, tile_column, tile_row)")
               << QStringLiteral("CREATE TABLE images (zoom_level integer, tile_data blob, tile_id text)")
               << QStringLiteral("CREATE UNIQUE INDEX images_id ON images (zoom_level, tile_id)")
               << QStringLiteral("CREATE VIEW tiles AS SELECT map.zoom_level AS zoom_level, map.tile_column AS tile_column,"
                                 " map.tile_row AS tile_row, images.tile_data AS tile_data FROM map JOIN images ON"
                                 " images.tile_id = map.tile_id AND images.zoom_level = map.zoom_level");
    else
        schema << QStringLiteral("CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")
               << QStringLiteral("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)");
    for (const QString& s : schema)
        if (!run(db, s, err))
            return false;

    const QString rowTable = mapImages ? QStringLiteral("map") : QStringLiteral("tiles");
    for (int i = 0; i < ms.size(); ++i) {
        const Member& m = ms[i];
        if (!run(db, QStringLiteral("ATTACH DATABASE ? AS m"), err, {m.pack.dir + QLatin1Char('/') + file}))
            return false;
        bool ok = run(db, QStringLiteral("BEGIN"), err);
        if (ok && mapImages) {
            // Plain INSERT: a tile in two members must fail, not be replaced. Identical tiles share one
            // image row (tile-join's tile_id is a hash of the tile data), so images ignore repeats.
            ok = run(db, QStringLiteral("INSERT INTO map SELECT zoom_level, tile_column, tile_row, tile_id FROM m.map"), err)
                && run(db, QStringLiteral("INSERT OR IGNORE INTO images SELECT zoom_level, tile_data, tile_id FROM m.images"), err);
        } else if (ok) {
            ok = run(db, QStringLiteral("INSERT INTO tiles SELECT zoom_level, tile_column, tile_row, tile_data FROM m.tiles"), err);
        }
        if (ok)
            ok = run(db, QStringLiteral("COMMIT"), err);
        if (!ok) {
            const QString sqlErr = err;
            QString ignore;
            run(db, QStringLiteral("ROLLBACK"), ignore);
            // A duplicate: find the first tile of this member already in the output.
            QSqlQuery q(db);
            const bool found = q.exec(QStringLiteral("SELECT a.zoom_level, a.tile_column, a.tile_row FROM m.%1 a JOIN main.%1 o ON"
                                                      " o.zoom_level = a.zoom_level AND o.tile_column = a.tile_column AND"
                                                      " o.tile_row = a.tile_row LIMIT 1").arg(rowTable)) && q.next();
            if (found) {
                const int z = q.value(0).toInt(), col = q.value(1).toInt(), row = q.value(2).toInt();
                QString other = ms.first().name;
                for (int j = 0; j < i; ++j)
                    if (memberHasTile(ms[j], file, z, col, row)) {
                        other = ms[j].name;
                        break;
                    }
                // Stored rows are TMS; the message gives z/x/y with y in XYZ (flipped), as maps and URLs read it.
                const qint64 y = (qint64(1) << z) - 1 - row;
                err = QStringLiteral("tile %1/%2/%3 is in both %4 and %5").arg(z).arg(col).arg(y).arg(other, m.name);
            } else {
                err = m.name + QStringLiteral(": ") + file + QStringLiteral(": ") + sqlErr;
            }
            return false;
        }
        if (!run(db, QStringLiteral("DETACH DATABASE m"), err))
            return false;
    }

    if (!run(db, QStringLiteral("BEGIN"), err))
        return false;
    for (const auto& kv : mergedMetadata(ms, charts, members, packSchema))
        if (!run(db, QStringLiteral("INSERT INTO metadata VALUES (?, ?)"), err, {kv.first, kv.second}))
            return false;
    return run(db, QStringLiteral("COMMIT"), err);
}

// "<file>: maxzoom differs: <packA> <za>, <packB> <zb>" when two fine members disagree.
QString maxzoomMismatch(const QList<Member>& ms, const QString& file) {
    const Member* first = nullptr;
    for (const Member& m : ms) {
        if (!m.hasTiles || m.maxZoom < kFineZoom)
            continue;
        if (!first)
            first = &m;
        else if (m.maxZoom != first->maxZoom)
            return QStringLiteral("%1: maxzoom differs: %2 %3, %4 %5").arg(file, first->name).arg(first->maxZoom).arg(m.name).arg(m.maxZoom);
    }
    return {};
}

std::expected<void, QString> mergeKind(const QList<PackInfo>& packs, const QString& kind, const QString& outDir) {
    const bool charts = kind == QLatin1String("charts");
    const QStringList& files = charts ? kChartsFiles : kBathyFiles;
    const QString dir = outDir + QLatin1Char('/') + kind;
    auto clean = [&] {
        const QDir d(dir);
        for (const QString& n : d.entryList({QStringLiteral("*.mbtiles"), QStringLiteral("*.tmp")}, QDir::Files))
            QFile::remove(d.filePath(n));
    };
    auto fail = [&](const QString& e) -> std::expected<void, QString> {
        clean();
        return std::unexpected(e);
    };
    if (!QDir().mkpath(dir))
        return std::unexpected(QStringLiteral("cannot create ") + dir);
    clean(); // stale output from an earlier run

    // The members, sorted by dir name, with their manifest hashes; their manifests must share one schema.
    QList<MergeMember> list;
    int schema = 0;
    QString schemaOf;
    for (const PackInfo& p : packs) {
        const QString name = QFileInfo(p.dir).fileName();
        QFile f(p.dir + QStringLiteral("/manifest.json"));
        if (!f.open(QIODevice::ReadOnly))
            return fail(name + QStringLiteral(": cannot read manifest.json"));
        const QByteArray bytes = f.readAll();
        const int s = QJsonDocument::fromJson(bytes).object().value(QStringLiteral("schema")).toInt();
        if (schemaOf.isEmpty()) {
            schema = s;
            schemaOf = name;
        } else if (s != schema) {
            return fail(QStringLiteral("schema differs: %1 %2, %3 %4").arg(schemaOf).arg(schema).arg(name).arg(s));
        }
        list.append({name, QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex())});
    }
    std::sort(list.begin(), list.end(), [](const MergeMember& a, const MergeMember& b) { return a.dir < b.dir; });
    QJsonArray members;
    for (const MergeMember& m : list)
        members.append(QJsonObject{{QStringLiteral("dir"), m.dir}, {QStringLiteral("manifest_sha256"), m.manifestSha256}});

    QStringList tmps;
    for (const QString& file : files) {
        QList<Member> ms;
        for (const PackInfo& p : packs) {
            QString err;
            const auto m = readMember(p, file, err);
            if (!m)
                return fail(err);
            ms.append(*m);
        }
        if (const QString e = maxzoomMismatch(ms, file); !e.isEmpty())
            return fail(e);
        const QString tmp = dir + QLatin1Char('/') + file + QStringLiteral(".tmp");
        tmps.append(tmp);
        QString err;
        if (!writeMerged(ms, file, charts, members, schema, tmp, err))
            return fail(err);
    }
    // All files are written; rename them last so a failure above leaves nothing behind.
    for (const QString& tmp : tmps) {
        const QString dest = tmp.chopped(4);
        if (!QFile::rename(tmp, dest))
            return fail(QStringLiteral("cannot rename ") + tmp);
    }
    return {};
}

} // namespace

std::expected<void, QString> mergePacks(const QList<PackInfo>& usable, const QString& outDir) {
    for (const QString& kind : {QStringLiteral("charts"), QStringLiteral("bathy")}) {
        QList<PackInfo> packs;
        for (const PackInfo& p : usable)
            if (p.kind == kind)
                packs.append(p);
        if (packs.size() < 2)
            continue;
        // Members are merged in region order so the first-wins rules do not depend on scan order.
        std::sort(packs.begin(), packs.end(), [](const PackInfo& a, const PackInfo& b) { return a.region < b.region; });
        if (auto r = mergeKind(packs, kind, outDir); !r)
            return r;
    }
    return {};
}

std::optional<QString> metadataValue(const QString& mbtilesPath, const QString& name) {
    if (!QFileInfo::exists(mbtilesPath))
        return std::nullopt;
    Conn c(mbtilesPath, true);
    if (!c.ok())
        return std::nullopt;
    QSqlQuery q(c.db());
    q.prepare(QStringLiteral("SELECT value FROM metadata WHERE name = ?"));
    q.addBindValue(name);
    if (!q.exec() || !q.next())
        return std::nullopt;
    return q.value(0).toString();
}

QList<MergeMember> mergeMembers(const QString& mbtilesPath) {
    const auto v = metadataValue(mbtilesPath, QStringLiteral("cheekymarine:members"));
    if (!v)
        return {};
    const QJsonDocument d = QJsonDocument::fromJson(v->toUtf8());
    if (!d.isArray())
        return {};
    QList<MergeMember> out;
    for (const QJsonValue& e : d.array()) {
        const QJsonObject o = e.toObject();
        const QJsonValue dir = o.value(QStringLiteral("dir")), sha = o.value(QStringLiteral("manifest_sha256"));
        if (!e.isObject() || !dir.isString() || !sha.isString())
            return {}; // the old list of plain names, or damaged
        out.append({dir.toString(), sha.toString()});
    }
    std::sort(out.begin(), out.end(), [](const MergeMember& a, const MergeMember& b) { return a.dir < b.dir; });
    return out;
}

std::optional<int> mergeSchema(const QString& mbtilesPath) {
    const auto v = metadataValue(mbtilesPath, QStringLiteral("cheekymarine:schema"));
    bool ok = false;
    const int s = v ? v->toInt(&ok) : 0;
    return ok ? std::optional<int>(s) : std::nullopt;
}

QList<double> mergeValdco(const QString& mbtilesPath) {
    QList<double> out;
    if (const auto v = metadataValue(mbtilesPath, QStringLiteral("cheekymarine:valdco")))
        for (const QJsonValue& e : QJsonDocument::fromJson(v->toUtf8()).array())
            out.append(num(e));
    std::sort(out.begin(), out.end());
    return out;
}

QList<LegendEntry> mergeLegend(const QString& mbtilesPath) {
    QList<LegendEntry> out;
    if (const auto v = metadataValue(mbtilesPath, QStringLiteral("cheekymarine:legend")))
        for (const QJsonValue& e : QJsonDocument::fromJson(v->toUtf8()).array()) {
            const QJsonObject o = e.toObject();
            out.append({o.value(QStringLiteral("abbr")).toString(), o.value(QStringLiteral("meaning")).toString(),
                        o.value(QStringLiteral("kind")).toString()});
        }
    return out;
}

QString manifestSha256(const QString& packDir) {
    QFile f(packDir + QStringLiteral("/manifest.json"));
    if (!f.open(QIODevice::ReadOnly))
        return {};
    return QString::fromLatin1(QCryptographicHash::hash(f.readAll(), QCryptographicHash::Sha256).toHex());
}
