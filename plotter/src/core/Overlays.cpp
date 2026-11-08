#include "Overlays.h"
#include <QJsonArray>
#include <cmath>

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kHeadingLineM = 50000.0;
constexpr double kAisVecSecs = 360.0;
constexpr double kMinCogSogMs = 0.2572;
constexpr double kHollowAgeSecs = 60.0;

double degNorm(double radians)
{
    double d = std::fmod(radians * 180.0 / kPi, 360.0);
    if (d < 0) d += 360.0;
    if (d >= 360.0) d = 0.0; // a tiny negative can round up to 360 after the add
    return d;
}

QJsonArray coord(LatLon p) { return QJsonArray{p.lon, p.lat}; }

QJsonObject feature(const QJsonObject& geometry, const QJsonObject& props)
{
    return QJsonObject{{"type", "Feature"}, {"geometry", geometry}, {"properties", props}};
}
QJsonObject point(LatLon p, const QJsonObject& props)
{
    return feature(QJsonObject{{"type", "Point"}, {"coordinates", coord(p)}}, props);
}
QJsonObject line(LatLon a, LatLon b, const QString& kind)
{
    return feature(QJsonObject{{"type", "LineString"}, {"coordinates", QJsonArray{coord(a), coord(b)}}},
                   QJsonObject{{"kind", kind}});
}
QJsonObject collection(const QJsonArray& features)
{
    return QJsonObject{{"type", "FeatureCollection"}, {"features", features}};
}
}

std::optional<double> trueHeadingDeg(const VesselState& v)
{
    if (!v.hdgRad) return std::nullopt;
    if (v.hdgRef == QLatin1String("True")) return degNorm(*v.hdgRad);
    if (v.hdgRef == QLatin1String("Magnetic") && v.variationRad) return degNorm(*v.hdgRad + *v.variationRad);
    return std::nullopt; // magnetic without variation, or no reference: not known to be true
}

std::optional<double> cogDeg(const VesselState& v)
{
    if (v.cogRad && v.sogMs && *v.sogMs > kMinCogSogMs) return degNorm(*v.cogRad);
    return std::nullopt;
}

QJsonObject ownShipGeoJson(const VesselState& v, const OwnShipOptions& opts)
{
    QJsonArray fs;
    if (!v.lat || !v.lon) return collection(fs);
    const LatLon pos{*v.lat, *v.lon};

    const std::optional<double> hdg = trueHeadingDeg(v), cog = cogDeg(v);
    fs.append(point(pos, QJsonObject{{"kind", "boat"}, {"rot", hdg.or_else([&] { return cog; }).value_or(0.0)}}));
    if (opts.heading && hdg) fs.append(line(pos, destination(pos, *hdg, kHeadingLineM), "heading"));
    if (opts.cog && cog) {
        const LatLon end = destination(pos, *cog, *v.sogMs * opts.cogSecs);
        fs.append(line(pos, end, "cog"));
        fs.append(point(end, QJsonObject{{"kind", "cogtip"}, {"rot", *cog}}));
    }
    return collection(fs);
}

QJsonObject tracksGeoJson(const QList<QList<LatLon>>& tracks)
{
    QJsonArray fs;
    for (const auto& t : tracks) {
        if (t.size() < 2) continue;
        QJsonArray coords;
        for (const LatLon& p : t) coords.append(coord(p));
        fs.append(feature(QJsonObject{{"type", "LineString"}, {"coordinates", coords}},
                          QJsonObject{{"kind", "track"}}));
    }
    return collection(fs);
}

QJsonObject aisGeoJson(const QList<AisTarget>& targets, const VesselState&)
{
    QJsonArray fs;
    for (const AisTarget& t : targets) {
        if (!t.lat || !t.lon) continue;
        const LatLon pos{*t.lat, *t.lon};
        const double rot = t.hdgRad ? degNorm(*t.hdgRad) : (t.cogRad ? degNorm(*t.cogRad) : 0.0);
        const bool hollow = t.posAge && *t.posAge > kHollowAgeSecs;
        fs.append(point(pos, QJsonObject{{"kind", "ais"},
                                         {"mmsi", static_cast<double>(t.mmsi)},
                                         {"cls", t.cls},
                                         {"rot", rot},
                                         {"hollow", hollow}}));
        if (t.cogRad && t.sogMs)
            fs.append(line(pos, destination(pos, degNorm(*t.cogRad), *t.sogMs * kAisVecSecs), "aisvec"));
    }
    return collection(fs);
}

QColor towardBlack(const QColor& c, double t)
{
    const auto ch = [t](int v) { return int(std::nearbyint(v * (1.0 - t))); };
    return QColor(ch(c.red()), ch(c.green()), ch(c.blue()));
}

// Day: a blue hull on the pack's cream, blue and grey water, AIS green, lines dark. Dusk: day toward
// black. Night: amber on black. The COG line and AIS vector are redder or darker than the chart's
// amber text (#E0A000, #C08000) so they stay apart from it.
OverlayColours overlayColours(const QString& palette)
{
    const auto c = [](const char* hex) { return QColor(QLatin1String(hex)); };
    if (palette == QLatin1String("night"))
        return {c("#7a5000"), c("#E0A000"), c("#2a1a08"), c("#0a0500"), c("#1a0e04"), c("#C08000"), c("#a02018"),
                c("#20A040"), c("#6a4400"), c("#C08000"), c("#D09000"), c("#D06000"), c("#A04800"), c("#A06800")};
    const OverlayColours day{c("#6E99BE"), c("#1e3448"), c("#d4d8dc"), c("#22303f"), c("#3a3f45"), c("#111111"),
                             c("#b85450"), c("#4f9a64"), c("#2e9e3e"), c("#000000"), c("#000000"), c("#000000"),
                             c("#000000"), c("#b000b0")};
    if (palette != QLatin1String("dusk")) return day;
    const auto d = [](const QColor& x) { return towardBlack(x, 0.45); };
    return {d(day.hullFill), d(day.hullOutline), d(day.cabin), d(day.windshield), d(day.motor), d(day.motorOutline),
            d(day.portLight), d(day.stbdLight), d(day.aisFill), d(day.aisOutline), d(day.heading), d(day.cog),
            d(day.aisVector), d(day.track)};
}

QColor trackColour(const QColor& chosen, const QString& palette)
{
    if (palette == QLatin1String("night")) return overlayColours(palette).track;
    if (palette == QLatin1String("dusk")) return towardBlack(chosen, 0.45);
    return chosen;
}
