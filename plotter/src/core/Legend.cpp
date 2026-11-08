#include "core/Legend.h"
#include "core/Overlays.h"
#include <QHash>
#include <QJsonArray>
#include <QStringList>

namespace {
constexpr double kMetersPerFoot = 0.3048;

// One legend row as data. `layers` are style layer ids; one ending in '*' stands for every layer
// whose id starts with the rest (the fish contour tiers). The row's color, tint, width, dash and icon
// size come from its first layer: fill-color (background-color, hillshade-shadow-color) for a swatch,
// line-color for a line, text-color for a text sample, icon-color (the fallback) as a sprite's tint.
// "%1" in `sprite` is the palette (the baked hazard images).
struct RowSpec {
    const char* label;
    const char* note;
    const char* kind;
    QStringList layers;
    const char* sprite = "";
    const char* text = "";
    const char* depthFrom = "";
    const char* depthTo = "";
};

// Category ids and titles, in order.
struct CategorySpec {
    const char* id;
    const char* title;
};
constexpr CategorySpec kAis{"ais", "AIS targets"};
constexpr CategorySpec kNavaids{"navaids", "Buoys and beacons"};
constexpr CategorySpec kLights{"lights", "Lights"};
constexpr CategorySpec kHazards{"hazards", "Hazards"};
constexpr CategorySpec kDepths{"depths", "Depths, areas and lines"};
constexpr CategorySpec kSeabed{"seabed", "Seabed"};

QList<RowSpec> navaidRows() {
    return {
        {"Nun buoy", "Cone top, usually red. Each buoy shows its charted color, gray if none.", "sprite", {"navaid"},
         "buoy-nun"},
        {"Can buoy", "Flat top, usually green.", "sprite", {"navaid"}, "buoy-can"},
        {"Spherical buoy", "Round top.", "sprite", {"navaid"}, "buoy-spherical"},
        {"Pillar buoy", "Tall tower; also any buoy whose shape is not charted.", "sprite", {"navaid"}, "buoy-pillar"},
        {"Spar buoy", "Pole shape.", "sprite", {"navaid"}, "buoy-spar"},
        {"Lateral beacon", "Fixed marker on a post or pile, red or green by side of the channel.", "sprite",
         {"navaid"}, "beacon-lateral"},
        {"Cardinal beacon", "Fixed marker showing which side of a hazard is clear.", "sprite", {"navaid"},
         "beacon-cardinal"},
        {"Other beacon", "Any other fixed marker.", "sprite", {"navaid"}, "beacon-generic"},
    };
}

QList<RowSpec> lightRows() {
    return {
        {"Light", "Flare in the light's charted color: white, red, green or yellow.", "sprite", {"light"},
         "light-flare"},
    };
}

QList<RowSpec> hazardRows() {
    return {
        {"Rock", "Underwater or awash rock.", "sprite", {"hazard"}, "hazard-rock-%1"},
        {"Wreck", "", "sprite", {"hazard"}, "hazard-wreck-%1"},
        {"Obstruction", "Anything else in the way, like a pile or snag.", "sprite", {"hazard"},
         "hazard-obstruction-%1"},
        {"Dangerous hazard", "Red dotted ring: shallower than your safety depth, no charted depth, or awash.",
         "sprite", {"hazard-danger"}, "hazard-rock-danger-%1"},
        {"Hazard area edge", "Dotted outline of a rocky, foul or wreck area.", "line", {"hazard-outline"}},
        {"Dangerous hazard area edge", "Red dotted outline: within your safety depth.", "line",
         {"hazard-danger-outline"}},
    };
}

// Base and areas first, then lines and labels; the nav and fish depth fills come before these.
QList<RowSpec> commonDepthRows() {
    return {
        {"Land", "", "swatch", {"lndare"}},
        {"No chart data", "Outside the charted area.", "swatch", {"background"}},
        {"Coastline", "", "line", {"coalne"}},
    };
}

QList<RowSpec> navDepthRows() {
    QList<RowSpec> rows{
        {"Very shallow", "", "swatch", {"depare-vshallow"}, "", "", "0", "shallow"},
        {"Shallow", "", "swatch", {"depare-shallow"}, "", "", "shallow", "safety"},
        {"Medium", "", "swatch", {"depare-medium"}, "", "", "safety", "deep"},
        {"Deep", "", "swatch", {"depare-deep"}, "", "", "deep", ""},
        {"Dries at low tide", "", "swatch", {"depare-intertidal"}},
    };
    rows += commonDepthRows();
    rows += QList<RowSpec>{
        {"Depth contour", "", "line", {"depcnt"}},
        {"Safety contour", "The contour at your safety depth.", "line", {"depcnt-safety"}},
        {"Sounding, shallow", "Depth in feet, shallower than your safety depth.", "text", {"soundg-shallow"}, "",
         "8"},
        {"Sounding, deep", "Depth in feet, at or deeper than your safety depth.", "text", {"soundg-deep"}, "", "42"},
        {"Restricted area edge", "", "line", {"area-resare"}},
        {"Restricted area ticks", "Along a restricted area's edge.", "sprite", {"area-resare-ticks"}, "resare-tick"},
        {"Anchorage area", "", "swatch", {"area-achare"}},
        {"Traffic separation zone", "Keep out between the shipping lanes.", "swatch", {"area-tsslpt"}},
        {"Cable or pipeline", "Do not anchor.", "line", {"line-cable"}},
        {"Ferry route or track", "Also navigation lines and recommended tracks.", "line", {"line-route"}},
        {"Sea area name", "", "text", {"area-names"}, "", "Name"},
        {"Kelp", "", "sprite", {"seabed-kelp"}, "kelp"},
    };
    return rows;
}

QList<RowSpec> fishDepthRows() {
    QList<RowSpec> rows{
        {"Water outside the fine survey", "Depth not surveyed in detail.", "swatch", {"water-base"}},
        {"Relief shading", "Shows the shape of the bottom.", "swatch", {"hillshade"}},
    };
    rows += commonDepthRows();
    rows += QList<RowSpec>{
        {"Minor contour", "", "line", {"contour-minor-*"}},
        {"Major contour", "", "line", {"contour-major"}},
        {"Coarse contour", "From the nautical chart: no fine survey here.", "line", {"contour-enc"}},
        {"Contour depth", "Depth in feet.", "text", {"contour-label", "contour-label-*"}, "", "60"},
        {"Kelp", "", "sprite", {"seabed-kelp"}, "kelp"},
    };
    return rows;
}

QList<RowSpec> seabedRows() {
    return {
        {"Seabed area", "Dashed edge; the label gives the bottom type, short forms below.", "line",
         {"seabed-cmecs", "seabed"}},
    };
}

QJsonObject findLayer(const QJsonObject& style, const QString& id) {
    for (const QJsonValue& l : style[QStringLiteral("layers")].toArray())
        if (l.toObject()[QStringLiteral("id")].toString() == id) return l.toObject();
    return {};
}

// The output values of a step or match expression, in order; empty for anything else.
QJsonArray outputs(const QJsonArray& e) {
    QJsonArray out;
    const QString op = e.isEmpty() ? QString() : e[0].toString();
    if (op == QLatin1String("step")) {
        for (qsizetype i = 2; i < e.size(); i += 2) out.append(e[i]);
    } else if (op == QLatin1String("match")) {
        for (qsizetype i = 3; i < e.size(); i += 2) out.append(e[i]);
        if (e.size() >= 3) out.append(e.last());
    }
    return out;
}

std::optional<double> literalNumber(const QJsonObject& layer, const char* group, const char* prop) {
    const QJsonValue v = layer[QLatin1String(group)].toObject()[QLatin1String(prop)];
    if (v.isDouble()) return v.toDouble();
    return std::nullopt;
}

QString colourText(const std::optional<QColor>& c) {
    if (!c || !c->isValid()) return {};
    return c->alpha() < 255 ? c->name(QColor::HexArgb) : c->name();
}

QVariantMap blankRow(const QString& label, const QString& note, const QString& kind) {
    return {{"label", label},          {"note", note},          {"kind", kind},
            {"color", QString()},     {"sprite", QString()},   {"tint", QString()},
            {"iconSize", 1.0},        {"dash", QVariantList()}, {"width", 0.0},
            {"text", QString()},      {"depthFrom", QString()}, {"depthTo", QString()},
            {"layers", QVariantList()}};
}

// Builds rows against one style; a row naming layers none of which the style has is left out.
class RowBuilder {
public:
    RowBuilder(const QJsonObject& style, const QString& palette) : m_style(style), m_palette(palette) {
        for (const QJsonValue& l : style[QStringLiteral("layers")].toArray())
            m_ids << l.toObject()[QStringLiteral("id")].toString();
    }

    QVariantList rows(const QList<RowSpec>& specs) const {
        QVariantList out;
        for (const RowSpec& s : specs)
            if (auto r = row(s)) out << *r;
        return out;
    }

    std::optional<QVariantMap> row(const RowSpec& s) const {
        QVariantList layers;
        for (const QString& pattern : s.layers)
            for (const QString& id : m_ids)
                if (pattern.endsWith(QLatin1Char('*')) ? id.startsWith(pattern.chopped(1)) : id == pattern)
                    layers << id;
        if (layers.isEmpty()) return std::nullopt;
        QVariantMap r =
            blankRow(QString::fromUtf8(s.label), QString::fromUtf8(s.note), QString::fromLatin1(s.kind));
        r["layers"] = layers;
        r["sprite"] = QString::fromLatin1(s.sprite).replace(QLatin1String("%1"), m_palette);
        r["text"] = QString::fromUtf8(s.text);
        r["depthFrom"] = QString::fromLatin1(s.depthFrom);
        r["depthTo"] = QString::fromLatin1(s.depthTo);

        const QString first = layers[0].toString();
        const QJsonObject layer = findLayer(m_style, first);
        const QString type = layer[QStringLiteral("type")].toString();
        const QString kind = r["kind"].toString();
        if (kind == QLatin1String("swatch")) {
            const QString prop = type == QLatin1String("background") ? QStringLiteral("background-color")
                                 : type == QLatin1String("hillshade") ? QStringLiteral("hillshade-shadow-color")
                                                                      : QStringLiteral("fill-color");
            std::optional<QColor> c = styleColour(m_style, first, prop);
            if (c && type == QLatin1String("fill"))
                if (const auto opacity = literalNumber(layer, "paint", "fill-opacity")) c->setAlphaF(*opacity);
            r["color"] = colourText(c);
        } else if (kind == QLatin1String("line")) {
            r["color"] = colourText(styleColour(m_style, first, QStringLiteral("line-color")));
            r["width"] = literalNumber(layer, "paint", "line-width").value_or(1.0);
            QVariantList dash;
            for (const QJsonValue& d : layer[QStringLiteral("paint")].toObject()[QStringLiteral("line-dasharray")]
                                           .toArray())
                if (d.isDouble()) dash << d.toDouble();
            r["dash"] = dash;
        } else if (kind == QLatin1String("text")) {
            r["color"] = colourText(styleColour(m_style, first, QStringLiteral("text-color")));
        } else if (kind == QLatin1String("sprite")) {
            r["tint"] = colourText(styleColour(m_style, first, QStringLiteral("icon-color")));
            r["iconSize"] = literalNumber(layer, "layout", "icon-size").value_or(1.0);
        }
        return r;
    }

    // The fish depth bands: one swatch per band-fill step output, its depths in meters from the
    // step stops on depth_min_ft.
    QVariantList fishBands() const {
        const QJsonArray e = findLayer(m_style, QStringLiteral("band-fill"))[QStringLiteral("paint")]
                                 .toObject()[QStringLiteral("fill-color")]
                                 .toArray();
        if (e.isEmpty() || e[0].toString() != QLatin1String("step")) return {};
        QStringList stops; // meters
        for (qsizetype i = 3; i < e.size(); i += 2) stops << QString::number(e[i].toDouble() * kMetersPerFoot);
        QVariantList out;
        const qsizetype n = stops.size() + 1;
        for (qsizetype k = 0; k < n; ++k) {
            // These are fishing survey bands, not safety depths: no name, the sheet shows the range.
            QVariantMap r = blankRow(QString(), QStringLiteral("Fish chart depth band, not a safety depth."),
                                     QStringLiteral("swatch"));
            r["color"] = colourText(styleColour(m_style, QStringLiteral("band-fill"), QStringLiteral("fill-color"),
                                                static_cast<int>(k)));
            r["depthFrom"] = k == 0 ? QStringLiteral("0") : stops[k - 1];
            r["depthTo"] = k + 1 < n ? stops[k] : QString();
            r["layers"] = QVariantList{QStringLiteral("band-fill")};
            out << r;
        }
        return out;
    }

private:
    const QJsonObject& m_style;
    QString m_palette;
    QStringList m_ids;
};

QVariantList aisRows(const QString& palette) {
    const OverlayColours c = overlayColours(palette);
    const auto overlay = [](const char* label, const char* note, const char* id) {
        QVariantMap r = blankRow(QString::fromUtf8(label), QString::fromUtf8(note), QStringLiteral("overlay"));
        r["sprite"] = QString::fromLatin1(id);
        return r;
    };
    QVariantMap vector = blankRow(QStringLiteral("Course vector"),
                                  QStringLiteral("Where the target will be in 6 minutes."), QStringLiteral("line"));
    vector["color"] = c.aisVector.name();
    vector["width"] = 1.5;
    return {
        overlay("Class A", "Ships and other large vessels.", OverlayIds::kAisImageA),
        overlay("Class B", "Smaller vessels.", OverlayIds::kAisImageB),
        overlay("Lost target", "No position report for over a minute.", OverlayIds::kAisImageHollow),
        vector,
    };
}

QVariantList seabedEntryRows(const QVariantList& seabed) {
    QVariantList out;
    for (const QVariant& e : seabed) {
        const QVariantMap m = e.toMap();
        QVariantMap r = blankRow(m["meaning"].toString(), QString(), QStringLiteral("seabed"));
        r["text"] = m["abbr"].toString();
        r["layers"] = QVariantList{QStringLiteral("seabed")};
        out << r;
    }
    return out;
}

QVariantMap categoryMap(const CategorySpec& c, const QVariantList& rows, bool needsPack) {
    return {{"id", QString::fromLatin1(c.id)},
            {"title", QString::fromLatin1(c.title)},
            {"rows", rows},
            {"needsPack", needsPack}};
}
} // namespace

std::optional<QColor> styleColour(const QJsonObject& style, const QString& layer, const QString& paintProp,
                                  int output) {
    const QJsonObject l = findLayer(style, layer);
    if (l.isEmpty()) return std::nullopt;
    const QJsonValue v = l[QStringLiteral("paint")].toObject()[paintProp];
    QJsonValue picked;
    if (v.isString()) {
        picked = v;
    } else if (v.isArray()) {
        const QJsonArray outs = outputs(v.toArray());
        if (output < 0 && !outs.isEmpty()) picked = outs.last();
        else if (output >= 0 && output < outs.size()) picked = outs[output];
    }
    if (!picked.isString()) return std::nullopt;
    const QColor c = QColor::fromString(picked.toString());
    if (!c.isValid()) return std::nullopt;
    return c;
}

QVariantList legendCategories(const QString& mode, const QJsonObject& style, const QString& palette,
                              const QVariantList& seabed) {
    const bool fish = mode == QLatin1String("fish");
    QVariantList out{categoryMap(kAis, aisRows(palette), false)};
    if (style.isEmpty()) {
        if (!fish) out << categoryMap(kNavaids, {}, true);
        for (const CategorySpec& c : {kLights, kHazards, kDepths, kSeabed}) out << categoryMap(c, {}, true);
        return out;
    }
    const RowBuilder b(style, palette);
    if (!fish) out << categoryMap(kNavaids, b.rows(navaidRows()), false);
    out << categoryMap(kLights, b.rows(lightRows()), false);
    out << categoryMap(kHazards, b.rows(hazardRows()), false);
    out << categoryMap(kDepths, fish ? b.fishBands() + b.rows(fishDepthRows()) : b.rows(navDepthRows()), false);
    out << categoryMap(kSeabed, b.rows(seabedRows()) + seabedEntryRows(seabed), false);
    return out;
}
