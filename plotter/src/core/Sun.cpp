#include "core/Sun.h"
#include <QList>
#include <QTimeZone>
#include <algorithm>
#include <cmath>
#include <utility>

// NOAA Solar Calculator equations (public domain, gml.noaa.gov/grad/solcalc/calcdetails.html, after
// Meeus, "Astronomical Algorithms"). Angles in degrees unless named *Rad.
namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr double kSunriseZenith = 90.833, kCivilZenith = 96.0;
constexpr double kUnixEpochJd = 2440587.5;

double rad(double deg) { return deg * kPi / 180.0; }
double deg(double r) { return r * 180.0 / kPi; }

struct SunPosition {
    double declination;  // degrees
    double eqTimeMin;    // equation of time, minutes
};

SunPosition sunPosition(double unixSecs) {
    const double jd = unixSecs / 86400.0 + kUnixEpochJd;
    const double t = (jd - 2451545.0) / 36525.0; // Julian century
    const double l0 = std::fmod(280.46646 + t * (36000.76983 + t * 0.0003032), 360.0);
    const double m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
    const double e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
    const double c = std::sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
                     std::sin(rad(2 * m)) * (0.019993 - 0.000101 * t) + std::sin(rad(3 * m)) * 0.000289;
    const double omega = 125.04 - 1934.136 * t;
    const double appLong = l0 + c - 0.00569 - 0.00478 * std::sin(rad(omega));
    const double meanObliq = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0;
    const double obliq = meanObliq + 0.00256 * std::cos(rad(omega));
    const double decl = deg(std::asin(std::sin(rad(obliq)) * std::sin(rad(appLong))));
    const double y = std::pow(std::tan(rad(obliq / 2)), 2);
    const double eqTime = 4.0 * deg(y * std::sin(2 * rad(l0)) - 2 * e * std::sin(rad(m)) +
                                    4 * e * y * std::sin(rad(m)) * std::cos(2 * rad(l0)) -
                                    0.5 * y * y * std::sin(4 * rad(l0)) - 1.25 * e * e * std::sin(2 * rad(m)));
    return {decl, eqTime};
}

// Zenith angle of the sun at an instant (no refraction), degrees.
double zenithAt(double unixSecs, double lat, double lon) {
    const SunPosition p = sunPosition(unixSecs);
    const double minOfDay = std::fmod(unixSecs / 60.0, 1440.0);
    const double trueSolarMin = std::fmod(minOfDay + p.eqTimeMin + 4.0 * lon + 1440.0, 1440.0);
    const double hourAngle = trueSolarMin / 4.0 - 180.0;
    const double cosZ = std::sin(rad(lat)) * std::sin(rad(p.declination)) +
                        std::cos(rad(lat)) * std::cos(rad(p.declination)) * std::cos(rad(hourAngle));
    return deg(std::acos(std::clamp(cosZ, -1.0, 1.0)));
}

// The time the sun crosses `zenith` on the solar day whose noon is near `noonGuess` (Unix seconds),
// rising (morning) or setting. Iterated so the sun position is taken at the event itself.
std::optional<double> crossing(double noonGuess, double lat, double lon, double zenith, bool rising) {
    double t = noonGuess;
    for (int i = 0; i < 5; ++i) {
        const SunPosition p = sunPosition(t);
        const double cosH = std::cos(rad(zenith)) / (std::cos(rad(lat)) * std::cos(rad(p.declination))) -
                            std::tan(rad(lat)) * std::tan(rad(p.declination));
        if (cosH < -1.0 || cosH > 1.0) return std::nullopt; // the sun stays above or below
        const double haDeg = deg(std::acos(cosH));
        // Solar noon in minutes after 00:00 UTC of the day of noonGuess.
        const double dayStart = std::floor(noonGuess / 86400.0) * 86400.0;
        const double noonMin = 720.0 - 4.0 * lon - p.eqTimeMin;
        const double eventMin = noonMin + (rising ? -4.0 : 4.0) * haDeg;
        const double next = dayStart + eventMin * 60.0;
        if (std::abs(next - t) < 1.0) return next;
        t = next;
    }
    return t;
}

enum class Kind { CivilDawn, Sunrise, Sunset, CivilDusk };

// Every event of the solar days whose noon falls within [from - 1 day, to + 1 day], sorted by time.
QList<std::pair<double, Kind>> eventsAround(double from, double to, double lat, double lon) {
    QList<std::pair<double, Kind>> out;
    // Solar noon is near 12:00 UTC - lon/15 h; take the solar days of every UTC day in range.
    const double first = std::floor(from / 86400.0) - 2, last = std::floor(to / 86400.0) + 2;
    for (double day = first; day <= last; ++day) {
        const double noon = day * 86400.0 + (720.0 - 4.0 * lon) * 60.0;
        const struct {
            double zenith;
            bool rising;
            Kind kind;
        } wanted[] = {{kCivilZenith, true, Kind::CivilDawn},
                      {kSunriseZenith, true, Kind::Sunrise},
                      {kSunriseZenith, false, Kind::Sunset},
                      {kCivilZenith, false, Kind::CivilDusk}};
        for (const auto& w : wanted)
            if (const auto t = crossing(noon, lat, lon, w.zenith, w.rising)) out.append({*t, w.kind});
    }
    std::sort(out.begin(), out.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    return out;
}

QDateTime toUtc(double unixSecs) {
    return QDateTime::fromSecsSinceEpoch(static_cast<qint64>(std::llround(unixSecs)), QTimeZone::UTC);
}
} // namespace

QString paletteName(Palette p) {
    switch (p) {
    case Palette::Day: return QStringLiteral("day");
    case Palette::Dusk: return QStringLiteral("dusk");
    case Palette::Night: return QStringLiteral("night");
    }
    return QStringLiteral("day");
}

SunEvents sunEvents(QDate utcDate, double lat, double lon) {
    const double start = double(QDateTime(utcDate, QTime(0, 0), QTimeZone::UTC).toSecsSinceEpoch());
    const double end = start + 86400.0;
    SunEvents e;
    for (const auto& [t, kind] : eventsAround(start, end, lat, lon)) {
        if (t < start || t >= end) continue;
        auto& slot = kind == Kind::CivilDawn ? e.civilDawn
                     : kind == Kind::Sunrise ? e.sunrise
                     : kind == Kind::Sunset  ? e.sunset
                                             : e.civilDusk;
        if (!slot) slot = toUtc(t); // the first, in the rare case a date holds two
    }
    return e;
}

Palette paletteAt(const QDateTime& utc, double lat, double lon) {
    const double now = double(utc.toSecsSinceEpoch());
    // The state after the last event at or before now, from the UTC dates before, of and after.
    const auto events = eventsAround(now - 86400.0, now + 86400.0, lat, lon);
    const std::pair<double, Kind>* last = nullptr;
    for (const auto& ev : events)
        if (ev.first <= now) last = &ev;
    if (last && now - last->first < 2 * 86400.0) {
        switch (last->second) {
        case Kind::CivilDawn: return Palette::Dusk;
        case Kind::Sunrise: return Palette::Day;
        case Kind::Sunset: return Palette::Dusk;
        case Kind::CivilDusk: return Palette::Night;
        }
    }
    // No event in reach (polar day or night): decide from the sun's altitude now.
    const double z = zenithAt(now, lat, lon);
    return z <= kSunriseZenith ? Palette::Day : z <= kCivilZenith ? Palette::Dusk : Palette::Night;
}
