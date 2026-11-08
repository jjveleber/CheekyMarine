#include "SpriteSheet.h"

#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <algorithm>
#include <cmath>

namespace {
// MapLibre SDF edge is 0.75 x 255 = 191; alpha ramps over +/- 16 around it.
constexpr int kEdge = 191;
constexpr int kHalfRamp = 16;
}

std::expected<SpriteSheet, QString> SpriteSheet::load(const QString& base) {
    QString stem;
    for (const QString& s : {base + "@2x", base}) {
        if (QFile::exists(s + ".json") && QFile::exists(s + ".png")) {
            stem = s;
            break;
        }
    }
    if (stem.isEmpty())
        return std::unexpected("sprite sheet not found: " + base);

    QFile f(stem + ".json");
    if (!f.open(QIODevice::ReadOnly))
        return std::unexpected("cannot read " + f.fileName());
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (!doc.isObject())
        return std::unexpected("bad sprite index " + f.fileName() + ": " + err.errorString());

    SpriteSheet sheet;
    sheet.m_sheet = QImage(stem + ".png").convertToFormat(QImage::Format_ARGB32);
    if (sheet.m_sheet.isNull())
        return std::unexpected("cannot read " + stem + ".png");

    const QJsonObject root = doc.object();
    for (auto it = root.begin(); it != root.end(); ++it) {
        const QJsonObject o = it.value().toObject();
        const QRect r(o["x"].toInt(), o["y"].toInt(), o["width"].toInt(), o["height"].toInt());
        if (r.isEmpty() || !sheet.m_sheet.rect().contains(r))
            continue;
        sheet.m_entries.insert(it.key(), {r, o["sdf"].toBool()});
    }
    return sheet;
}

bool SpriteSheet::contains(const QString& name) const {
    return m_entries.contains(name);
}

QImage SpriteSheet::image(const QString& name, const std::optional<QColor>& tint) const {
    const auto it = m_entries.constFind(name);
    if (it == m_entries.constEnd())
        return {};
    QImage out = m_sheet.copy(it->rect);
    if (!it->sdf)
        return out;

    const QColor c = tint.value_or(QColor(Qt::black));
    for (int y = 0; y < out.height(); ++y) {
        auto* line = reinterpret_cast<QRgb*>(out.scanLine(y));
        for (int x = 0; x < out.width(); ++x) {
            const double t = (qAlpha(line[x]) - (kEdge - kHalfRamp)) / double(2 * kHalfRamp);
            const int a = int(std::lround(std::clamp(t, 0.0, 1.0) * 255.0));
            // premultiplied-free ARGB32: store straight color with computed alpha
            line[x] = qRgba(c.red(), c.green(), c.blue(), a);
        }
    }
    return out;
}
