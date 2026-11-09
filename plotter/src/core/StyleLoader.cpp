#include "core/StyleLoader.h"
#include <QDir>
#include <QJsonValue>
#include <QStringList>

std::expected<QString, QString> tileUrl(const QString& absMbtilesPath) {
    if (!QDir::isAbsolutePath(absMbtilesPath))
        return std::unexpected(QStringLiteral("tile path is not absolute: ") + absMbtilesPath);
    if (absMbtilesPath.contains(QLatin1Char('?')) || absMbtilesPath.contains(QLatin1Char('%')))
        return std::unexpected(QStringLiteral("tile path contains '?' or '%': ") + absMbtilesPath);
    return QStringLiteral("mbtiles://") + absMbtilesPath;
}

namespace {
const QStringList kSourceNames{"enc", "bathy", "dem", "bathy-coarse", "dem-coarse"};
}

std::expected<QJsonObject, QString> rewriteStyle(QJsonObject style, const QString& packDir,
                                                 const QHash<QString, QString>& sourceFiles) {
    const QString prefix = QStringLiteral("mbtiles://");
    QJsonObject sources = style.value(QStringLiteral("sources")).toObject();
    for (auto it = sources.begin(); it != sources.end(); ++it) {
        const QString name = it.key();
        if (!kSourceNames.contains(name))
            return std::unexpected(QStringLiteral("unknown source: ") + name);
        QJsonObject src = it.value().toObject();
        if (src.value(QStringLiteral("url")).toString() != prefix + name)
            return std::unexpected(QStringLiteral("source %1 url is not %2%1").arg(name, prefix));
        const auto file = sourceFiles.constFind(name);
        if (file == sourceFiles.constEnd())
            return std::unexpected(QStringLiteral("source %1 needs a pack that is not there").arg(name));
        auto url = tileUrl(*file);
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
