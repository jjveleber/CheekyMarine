#pragma once

#include <QColor>
#include <QHash>
#include <QImage>
#include <QRect>
#include <QString>
#include <expected>
#include <optional>

// A MapLibre sprite sheet (JSON index + PNG). SDF entries are returned tinted.
class SpriteSheet {
public:
    // base is the path without extension; reads base@2x.json/.png, else base.json/.png.
    static std::expected<SpriteSheet, QString> load(const QString& base);

    // Null QImage for an unknown name. A non-SDF entry is the cropped RGBA (tint ignored).
    QImage image(const QString& name, const std::optional<QColor>& tint) const;
    bool contains(const QString& name) const;

private:
    struct Entry {
        QRect rect;
        bool sdf = false;
    };
    QImage m_sheet;
    QHash<QString, Entry> m_entries;
};
