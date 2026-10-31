#include "core/StyleLoader.h"
#include <QDir>
#include <QJsonValue>

std::expected<QString, QString> tileUrl(const QString& absMbtilesPath) {
    if (!QDir::isAbsolutePath(absMbtilesPath))
        return std::unexpected(QStringLiteral("tile path is not absolute: ") + absMbtilesPath);
    if (absMbtilesPath.contains(QLatin1Char('?')) || absMbtilesPath.contains(QLatin1Char('%')))
        return std::unexpected(QStringLiteral("tile path contains '?' or '%': ") + absMbtilesPath);
    return QStringLiteral("mbtiles://") + absMbtilesPath;
}

std::expected<QJsonObject, QString> rewriteStyle(QJsonObject style, const QString& packDir,
                                                 const QString& chartsDir, const QString& bathyDir) {
    const QString prefix = QStringLiteral("mbtiles://");
    QJsonObject sources = style.value(QStringLiteral("sources")).toObject();
    for (auto it = sources.begin(); it != sources.end(); ++it) {
        const QString name = it.key();
        if (name != QLatin1String("enc") && name != QLatin1String("bathy") && name != QLatin1String("dem"))
            return std::unexpected(QStringLiteral("unknown source: ") + name);
        QJsonObject src = it.value().toObject();
        if (src.value(QStringLiteral("url")).toString() != prefix + name)
            return std::unexpected(QStringLiteral("source %1 url is not %2%1").arg(name, prefix));
        const QString dir = name == QLatin1String("enc") ? chartsDir : bathyDir;
        if (dir.isEmpty()) return std::unexpected(QStringLiteral("source %1 needs a pack that is not there").arg(name));
        auto url = tileUrl(dir + QLatin1Char('/') + name + QStringLiteral(".mbtiles"));
        if (!url) return std::unexpected(url.error());
        src[QStringLiteral("url")] = *url;
        it.value() = src;
    }
    style[QStringLiteral("sources")] = sources;

    if (style.contains(QStringLiteral("sprite"))) {
        const QString sprite = style.value(QStringLiteral("sprite")).toString();
        const QString sp = QStringLiteral("pack://sprites/");
        const QString leaf = sprite.mid(sp.size());
        if (!sprite.startsWith(sp) || leaf.isEmpty() || leaf.contains(QLatin1Char('/')))
            return std::unexpected(QStringLiteral("unexpected sprite value: ") + sprite);
        style[QStringLiteral("sprite")] = QStringLiteral("file://") + packDir + QStringLiteral("/sprites/") + leaf;
    }
    if (style.contains(QStringLiteral("glyphs"))) {
        const QString glyphs = style.value(QStringLiteral("glyphs")).toString();
        if (glyphs != QLatin1String("pack://glyphs/{fontstack}/{range}.pbf"))
            return std::unexpected(QStringLiteral("unexpected glyphs value: ") + glyphs);
        style[QStringLiteral("glyphs")] =
            QStringLiteral("file://") + packDir + QStringLiteral("/glyphs/{fontstack}/{range}.pbf");
    }
    return style;
}
