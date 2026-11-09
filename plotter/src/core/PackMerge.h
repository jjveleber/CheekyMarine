#pragma once
#include "core/PackCatalog.h"
#include <QList>
#include <QString>
#include <QStringList>
#include <expected>
#include <optional>

// One member pack of a merged MBTiles: its directory name and the SHA-256 (lowercase hex) of its
// manifest.json when it was merged.
struct MergeMember {
    QString dir;
    QString manifestSha256;
    bool operator==(const MergeMember&) const = default;
};

// For each pack kind with two or more packs in `usable`, writes outDir/<kind>/<file> for every file
// of that kind (kChartsFiles, kBathyFiles): one MBTiles holding the tiles of all member packs. A
// kind with fewer than two packs writes nothing. On any error no file of that kind is left in
// outDir/<kind>, and the error names the packs and files involved. Each file records its members
// (cheekymarine:members) and their shared manifest schema (cheekymarine:schema); members whose
// schemas differ are an error.
std::expected<void, QString> mergePacks(const QList<PackInfo>& usable, const QString& outDir);

// The members recorded in a merged MBTiles (cheekymarine:members), sorted by dir; empty when the
// file is unreadable, has none, or holds the old list of plain dir names.
QList<MergeMember> mergeMembers(const QString& mbtilesPath);

// The cheekymarine:schema of a merged MBTiles; nullopt when unreadable, absent or not a whole number.
std::optional<int> mergeSchema(const QString& mbtilesPath);

// The cheekymarine:valdco of a merged charts MBTiles (the union over its members), ascending; empty
// when unreadable or absent.
QList<double> mergeValdco(const QString& mbtilesPath);

// The cheekymarine:legend of a merged charts MBTiles (the union over its members' legend.json, first
// wins per abbr and kind); empty when unreadable or absent.
QList<LegendEntry> mergeLegend(const QString& mbtilesPath);

// The value of metadata `name` in an MBTiles; nullopt when the file or the row cannot be read.
std::optional<QString> metadataValue(const QString& mbtilesPath, const QString& name);

// The SHA-256 (lowercase hex) of packDir/manifest.json; empty when it cannot be read.
QString manifestSha256(const QString& packDir);
