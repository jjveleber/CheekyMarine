#pragma once
#include "core/PackCatalog.h"
#include <QList>
#include <QString>
#include <QStringList>
#include <expected>

// For each pack kind with two or more packs in `usable`, writes outDir/<kind>/<file> for every file
// of that kind (kChartsFiles, kBathyFiles): one MBTiles holding the tiles of all member packs. A
// kind with fewer than two packs writes nothing. On any error no file of that kind is left in
// outDir/<kind>, and the error names the packs and files involved.
std::expected<void, QString> mergePacks(const QList<PackInfo>& usable, const QString& outDir);

// The member pack directory names recorded in a merged MBTiles (cheekymarine:members); empty when
// the file is unreadable or has none.
QStringList mergeMembers(const QString& mbtilesPath);
