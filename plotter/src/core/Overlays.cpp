#include "Overlays.h"
#include <QJsonArray>
#include <cmath>

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kHeadingLineM = 50000.0;
constexpr double kCogSecs = 120.0, kAisVecSecs = 360.0;
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

QJsonObject ownShipGeoJson(const VesselState& v)
{
    QJsonArray fs;
    if (!v.lat || !v.lon) return collection(fs);
    const LatLon pos{*v.lat, *v.lon};

    std::optional<double> hdgTrue;
    if (v.hdgRad) {
        double h = *v.hdgRad;
        if (v.hdgRef == QLatin1String("Magnetic") && v.variationRad) h += *v.variationRad;
        hdgTrue = h;
    }
    const double rot = hdgTrue ? degNorm(*hdgTrue) : (v.cogRad ? degNorm(*v.cogRad) : 0.0);
    fs.append(point(pos, QJsonObject{{"kind", "boat"}, {"rot", rot}}));
    if (hdgTrue) fs.append(line(pos, destination(pos, degNorm(*hdgTrue), kHeadingLineM), "heading"));
    if (v.cogRad && v.sogMs && *v.sogMs > kMinCogSogMs)
        fs.append(line(pos, destination(pos, degNorm(*v.cogRad), *v.sogMs * kCogSecs), "cog"));
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

// Own boat orange (reads on the pack's cream, blue and grey water), AIS green, lines dark. Night:
// a dark red fill under a bright red outline, red lines.
OverlayColours overlayColours(const QString& palette) {
    if (palette == QLatin1String("night"))
        return {QColor(0x50, 0x00, 0x00), QColor(0xff, 0x00, 0x00), QColor(0x30, 0x00, 0x00), QColor(0xc0, 0x00, 0x00),
                QColor(0xe0, 0x00, 0x00), QColor(0xe0, 0x00, 0x00), QColor(0xa0, 0x00, 0x00), QColor(0x90, 0x00, 0x00)};
    if (palette == QLatin1String("dusk"))
        return {QColor(0xe0, 0x70, 0x00), QColor(0x00, 0x00, 0x00), QColor(0x2a, 0x8a, 0x36), QColor(0x00, 0x00, 0x00),
                QColor(0x10, 0x10, 0x10), QColor(0x10, 0x10, 0x10), QColor(0x10, 0x10, 0x10), QColor(0xd0, 0x40, 0xd0)};
    return {QColor(0xff, 0x80, 0x00), QColor(0x00, 0x00, 0x00), QColor(0x2e, 0x9e, 0x3e), QColor(0x00, 0x00, 0x00),
            QColor(0x00, 0x00, 0x00), QColor(0x00, 0x00, 0x00), QColor(0x00, 0x00, 0x00), QColor(0xb0, 0x00, 0xb0)};
}
