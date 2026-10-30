#include "Fields.h"
#include <QDateTime>
#include <cmath>

namespace {
const QString kMissing = QStringLiteral("--");
constexpr double kPi = 3.14159265358979323846;

// Round half away from zero (std::round) to one decimal; always prints one decimal.
double round1(double v) { return std::round(v * 10.0) / 10.0; }
QString oneDecimal(double v) { return QString::number(round1(v), 'f', 1); }
QString whole(double v) { return QString::number(static_cast<long long>(std::round(v))); }

QString degrees3(double rad) {
    double d = std::fmod(rad * 180.0 / kPi, 360.0);
    if (d < 0) d += 360.0;
    long long n = static_cast<long long>(std::round(d)) % 360;
    return QStringLiteral("%1").arg(n, 3, 10, QLatin1Char('0'));
}

QString coord(double v, QChar pos, QChar neg, int degWidth) {
    const QChar h = v < 0 ? neg : pos;
    // Thousandths of a minute, so rounding carries into degrees correctly.
    long long tm = static_cast<long long>(std::round(std::fabs(v) * 60.0 * 1000.0));
    long long deg = tm / 60000;
    long long rem = tm % 60000;
    return QStringLiteral("%1°%2.%3'%4")
        .arg(deg, degWidth, 10, QLatin1Char('0'))
        .arg(rem / 1000, 2, 10, QLatin1Char('0'))
        .arg(rem % 1000, 3, 10, QLatin1Char('0'))
        .arg(h);
}

struct NameEntry {
    Field f;
    const char16_t* name;
};
const NameEntry kNames[] = {
    {Field::Depth, u"depth"}, {Field::Sog, u"sog"},         {Field::Stw, u"stw"},
    {Field::Cog, u"cog"},     {Field::Heading, u"hdg"},     {Field::WaterTemp, u"wtemp"},
    {Field::Position, u"pos"}, {Field::Time, u"time"},      {Field::Rpm, u"rpm"},
};
}  // namespace

QString formatValue(Field f, const VesselState& s, const UnitPrefs& p) {
    switch (f) {
    case Field::Depth: {
        if (!s.depthM) return kMissing;
        double m = *s.depthM;
        if (p.applyDepthOffset && s.depthOffsetM) m += *s.depthOffsetM;
        double v = m;
        if (p.depth == DepthUnit::Feet) v = m / 0.3048;
        else if (p.depth == DepthUnit::Fathoms) v = m / 1.8288;
        return round1(v) >= 10.0 ? whole(v) : oneDecimal(v);
    }
    case Field::Sog:
    case Field::Stw: {
        const auto& ms = f == Field::Sog ? s.sogMs : s.stwMs;
        if (!ms) return kMissing;
        double k = p.speed == SpeedUnit::Knots ? 3600.0 / 1852.0
                 : p.speed == SpeedUnit::Mph   ? 3600.0 / 1609.344
                                               : 3.6;
        return oneDecimal(*ms * k);
    }
    case Field::Cog:
        return s.cogRad ? degrees3(*s.cogRad) : kMissing;
    case Field::Heading:
        return s.hdgRad ? degrees3(*s.hdgRad) : kMissing;
    case Field::WaterTemp: {
        if (!s.waterTempK) return kMissing;
        double c = *s.waterTempK - 273.15;
        return oneDecimal(p.temp == TempUnit::C ? c : c * 9.0 / 5.0 + 32.0);
    }
    case Field::Position:
        if (!s.lat || !s.lon) return kMissing;
        return coord(*s.lat, QLatin1Char('N'), QLatin1Char('S'), 2) + QLatin1Char('\n') +
               coord(*s.lon, QLatin1Char('E'), QLatin1Char('W'), 3);
    case Field::Time: {
        // No gnssTime and no sample time yet means nothing to show.
        if (!s.gnssTime && s.t <= 0) return kMissing;
        double secs = s.gnssTime ? *s.gnssTime : s.t;
        return QDateTime::fromSecsSinceEpoch(static_cast<qint64>(std::floor(secs)))
            .toLocalTime()
            .toString(QStringLiteral("HH:mm:ss"));
    }
    case Field::Rpm:
        return s.rpm ? whole(*s.rpm) : kMissing;
    }
    return kMissing;
}

QString unitLabel(Field f, const VesselState& s, const UnitPrefs& p) {
    switch (f) {
    case Field::Depth:
        return p.depth == DepthUnit::Feet     ? QStringLiteral("ft")
               : p.depth == DepthUnit::Metres ? QStringLiteral("m")
                                              : QStringLiteral("fm");
    case Field::Sog:
    case Field::Stw:
        return p.speed == SpeedUnit::Knots  ? QStringLiteral("kn")
               : p.speed == SpeedUnit::Mph  ? QStringLiteral("mph")
                                            : QStringLiteral("km/h");
    case Field::Cog:
        return QStringLiteral("°T");
    case Field::Heading:
        return s.hdgRef == QLatin1String("Magnetic") ? QStringLiteral("°M")
               : s.hdgRef == QLatin1String("True")   ? QStringLiteral("°T")
                                                     : QStringLiteral("°");
    case Field::WaterTemp:
        return p.temp == TempUnit::F ? QStringLiteral("°F") : QStringLiteral("°C");
    case Field::Rpm:
        return QStringLiteral("rpm");
    case Field::Position:
    case Field::Time:
        return QString();
    }
    return QString();
}

QString fieldName(Field f) {
    for (const auto& e : kNames)
        if (e.f == f) return QString::fromUtf16(e.name);
    return QString();
}

std::optional<Field> fieldFromName(QStringView n) {
    for (const auto& e : kNames)
        if (n == QStringView(e.name)) return e.f;
    return std::nullopt;
}
