#pragma once
#include <QJsonObject>
#include <QString>
#include <expected>

// "mbtiles://" + absPath. Error for a relative path or one containing '?' or '%', which MapLibre's
// MBTiles file source cannot take.
std::expected<QString, QString> tileUrl(const QString& absMbtilesPath);

// Turns a pack's shipped style into one MapLibre can load from local files. `packDir` holds
// sprites/ and glyphs/ (charts pack for nav styles, bathy pack for fish styles). Nothing but the
// sources' urls, `sprite` and `glyphs` changes.
std::expected<QJsonObject, QString> rewriteStyle(QJsonObject style, const QString& packDir,
                                                 const QString& chartsDir, const QString& bathyDir);
