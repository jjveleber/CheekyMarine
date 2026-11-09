#pragma once
#include <QHash>
#include <QJsonObject>
#include <QString>
#include <expected>

// "mbtiles://" + absPath. Error for a relative path or one containing '?' or '%', which MapLibre's
// MBTiles file source cannot take.
std::expected<QString, QString> tileUrl(const QString& absMbtilesPath);

// Turns a pack's shipped style into one MapLibre can load from local files. `packDir` holds
// sprites/ and glyphs/ (charts pack for nav styles, bathy pack for fish styles). Nothing but the
// sources' urls, `sprite` and `glyphs` changes. A style with no `sprite` or no `glyphs` key passes
// through unchanged: the pack contract does not require either key. Sources must be named `enc`,
// `bathy`, `dem`, `bathy-coarse` or `dem-coarse` with url `mbtiles://<name>`; each takes
// tileUrl(sourceFiles[name]), and a name missing from `sourceFiles` is an error.
std::expected<QJsonObject, QString> rewriteStyle(QJsonObject style, const QString& packDir,
                                                 const QHash<QString, QString>& sourceFiles);
