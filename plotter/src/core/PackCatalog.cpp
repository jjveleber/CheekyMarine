#include "core/PackCatalog.h"
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRandomGenerator>
#include <QRegularExpression>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <algorithm>

namespace {

// Reads cheekymarine:valdco, minzoom and maxzoom from an MBTiles file. False when the file cannot be
// read as MBTiles (not SQLite, no metadata table) or valdco is present but not a JSON array of numbers.
bool readMetadata(const QString& path, QList<double>& valdco, int& minZoom, int& maxZoom) {
    const QString conn = QStringLiteral("packcatalog-") + QString::number(QRandomGenerator::global()->generate64(), 16);
    bool ok = true;
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), conn);
        db.setDatabaseName(path);
        db.setConnectOptions(QStringLiteral("QSQLITE_OPEN_READONLY"));
        QSqlQuery q(db);
        if (!db.open() || !q.exec(QStringLiteral("SELECT name, value FROM metadata"))) {
            ok = false;
        } else {
            while (q.next()) {
                const QString k = q.value(0).toString();
                const QString v = q.value(1).toString();
                if (k == QLatin1String("minzoom")) {
                    bool good = false;
                    const int z = v.toInt(&good);
                    if (good)
                        minZoom = z;
                } else if (k == QLatin1String("maxzoom")) {
                    bool good = false;
                    const int z = v.toInt(&good);
                    if (good)
                        maxZoom = z;
                } else if (k == QLatin1String("cheekymarine:valdco")) {
                    const QJsonDocument d = QJsonDocument::fromJson(v.toUtf8());
                    if (!d.isArray()) {
                        ok = false;
                        break;
                    }
                    for (const QJsonValue& e : d.array()) {
                        bool good = e.isDouble();
                        const double x = e.isString() ? e.toString().toDouble(&good) : e.toDouble();
                        if (!good) {
                            ok = false;
                            break;
                        }
                        valdco.append(x);
                    }
                    if (!ok)
                        break;
                }
            }
        }
        db.close();
    } // no QSqlDatabase or QSqlQuery copy may be alive when the connection is removed
    QSqlDatabase::removeDatabase(conn);
    std::sort(valdco.begin(), valdco.end());
    return ok;
}

// legend.json entries; empty unless the file parses and has schema 1.
QList<LegendEntry> readLegend(const QString& path) {
    QList<LegendEntry> out;
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return out;
    const QJsonDocument d = QJsonDocument::fromJson(f.readAll());
    if (!d.isObject() || d.object().value(QStringLiteral("schema")).toInt(-1) != 1)
        return out;
    for (const QJsonValue& v : d.object().value(QStringLiteral("entries")).toArray()) {
        const QJsonObject o = v.toObject();
        out.append({o.value(QStringLiteral("abbr")).toString(), o.value(QStringLiteral("meaning")).toString(),
                    o.value(QStringLiteral("kind")).toString()});
    }
    return out;
}

bool hasStyles(const QString& dir) {
    return !QDir(dir + QStringLiteral("/styles")).entryList({QStringLiteral("*.json")}, QDir::Files).isEmpty();
}

} // namespace

QList<PackInfo> PackCatalog::scan(const QString& dir) {
    static const QRegularExpression nameRe(QStringLiteral("^(charts|bathy)-([a-z0-9-]+)-(\\d+\\.\\d+\\.\\d+)$"));
    QList<PackInfo> out;
    const QDir root(dir);
    for (const QFileInfo& fi : root.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name)) {
        const QRegularExpressionMatch m = nameRe.match(fi.fileName());
        if (!m.hasMatch())
            continue;
        PackInfo p;
        p.kind = m.captured(1);
        p.region = m.captured(2);
        p.version = QVersionNumber::fromString(m.captured(3));
        p.dir = fi.absoluteFilePath();

        QFile mf(p.dir + QStringLiteral("/manifest.json"));
        if (!mf.exists()) {
            p.refused = QStringLiteral("no manifest.json");
            out.append(p);
            continue;
        }
        QJsonParseError pe;
        const QJsonDocument doc = mf.open(QIODevice::ReadOnly) ? QJsonDocument::fromJson(mf.readAll(), &pe)
                                                                 : QJsonDocument();
        if (!doc.isObject()) {
            p.refused = QStringLiteral("manifest unreadable");
            out.append(p);
            continue;
        }
        const QJsonObject mo = doc.object();
        p.notice = mo.value(QStringLiteral("notice")).toString();
        const QJsonValue schema = mo.value(QStringLiteral("schema"));
        if (schema.isUndefined()) {
            p.refused = QStringLiteral("schema missing");
        } else if (!schema.isDouble()) {
            p.refused = QStringLiteral("schema is not a number");
        } else if (schema.toDouble() != 1) {
            p.refused = QStringLiteral("schema %1 not supported").arg(schema.toDouble());
        } else if (mo.value(QStringLiteral("pack")).toString() != p.kind
                   || mo.value(QStringLiteral("region")).toString() != p.region
                   || mo.value(QStringLiteral("version")).toString() != m.captured(3)) {
            p.refused = QStringLiteral("name does not match manifest");
        } else {
            const QStringList files = p.kind == QLatin1String("charts")
                ? QStringList{QStringLiteral("enc.mbtiles")}
                : QStringList{QStringLiteral("bathy.mbtiles"), QStringLiteral("dem.mbtiles")};
            for (const QString& f : files) {
                if (!QFileInfo::exists(p.dir + QLatin1Char('/') + f)) {
                    p.refused = QStringLiteral("missing ") + f;
                    break;
                }
            }
            if (p.refused.isEmpty() && !hasStyles(p.dir))
                p.refused = QStringLiteral("styles missing");
            // A pack whose enc.mbtiles cannot be read is refused: its safety contour values are unknown.
            if (p.refused.isEmpty() && p.kind == QLatin1String("charts")
                && !readMetadata(p.dir + QStringLiteral("/enc.mbtiles"), p.valdco, p.minZoom, p.maxZoom)) {
                p.valdco.clear();
                p.minZoom = p.maxZoom = -1;
                p.refused = QStringLiteral("enc.mbtiles unreadable");
            }
            if (p.refused.isEmpty() && p.kind == QLatin1String("charts"))
                p.legend = readLegend(p.dir + QStringLiteral("/legend.json"));
        }
        out.append(p);
    }
    return out;
}

std::optional<PackInfo> PackCatalog::best(const QList<PackInfo>& packs, QStringView kind, QStringView region) {
    std::optional<PackInfo> b;
    for (const PackInfo& p : packs) {
        if (!p.refused.isEmpty() || p.kind != kind || (!region.isEmpty() && p.region != region))
            continue;
        if (!b || p.version > b->version)
            b = p;
    }
    return b;
}
