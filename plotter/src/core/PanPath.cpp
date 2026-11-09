#include "core/PanPath.h"

std::expected<QList<PanPoint>, QString> parsePanPath(const QString& text)
{
    QList<PanPoint> out;
    for (const QString& item : text.split(';', Qt::SkipEmptyParts)) {
        const QStringList parts = item.split(',');
        if (parts.size() != 3) return std::unexpected(QStringLiteral("want lat,lon,zoom, got '%1'").arg(item));
        double v[3];
        for (int i = 0; i < 3; ++i) {
            bool ok = false;
            v[i] = parts[i].trimmed().toDouble(&ok);
            if (!ok) return std::unexpected(QStringLiteral("not a number: '%1'").arg(parts[i]));
        }
        out.append({v[0], v[1], v[2]});
    }
    if (out.size() < 2) return std::unexpected(QStringLiteral("want at least 2 points, got %1").arg(out.size()));
    return out;
}

PanPoint panAt(const QList<PanPoint>& path, qint64 legMs, qint64 tMs)
{
    const qint64 n = path.size();
    const qint64 leg = (tMs / legMs) % n;
    const double f = double(tMs % legMs) / double(legMs);
    const PanPoint& a = path[leg];
    const PanPoint& b = path[(leg + 1) % n];
    return {a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f, a.zoom + (b.zoom - a.zoom) * f};
}
