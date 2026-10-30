#pragma once
#include <QList>
#include <QString>
#include <QStringView>
#include <QVersionNumber>
#include <optional>

// One installed chart or bathy pack. `refused` empty means usable; otherwise it is the reason
// shown on the About page.
struct PackInfo {
    QString kind;   // "charts" or "bathy"
    QString region;
    QVersionNumber version;
    QString dir;    // absolute path of the pack directory
    QString notice;
    QList<double> valdco; // charts only, ascending
    int minZoom = -1;     // charts only, from enc.mbtiles metadata; -1 when absent
    int maxZoom = -1;
    QString refused;
};

class PackCatalog {
public:
    // Scans `dir` for charts-<region>-<x.y.z> and bathy-<region>-<x.y.z> directories. A broken pack
    // is returned with `refused` set, never a crash. Other entries are ignored.
    static QList<PackInfo> scan(const QString& dir);
    // Highest version among non-refused packs of `kind` (and `region` when non-empty).
    static std::optional<PackInfo> best(const QList<PackInfo>& packs, QStringView kind, QStringView region = {});
};
