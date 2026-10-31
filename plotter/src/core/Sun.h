#pragma once
#include <QDate>
#include <QDateTime>
#include <QString>
#include <optional>

enum class Palette { Day, Dusk, Night };

// "day", "dusk" or "night".
QString paletteName(Palette p);

// Sun events of one UTC date, in UTC. An event is absent when it does not fall within that date
// (it moved to the date before or after, or the sun does not reach that altitude at all).
struct SunEvents {
    std::optional<QDateTime> civilDawn, sunrise, sunset, civilDusk;
};

// NOAA solar position equations (public domain, the NOAA Solar Calculator): sunrise and sunset at
// zenith 90.833 deg (refraction and the sun's radius), civil dawn and dusk at 96 deg. Latitude north
// positive, longitude east positive, degrees.
SunEvents sunEvents(QDate utcDate, double lat, double lon);

// Day between sunrise and sunset, dusk between civil dawn and sunrise and between sunset and civil
// dusk, night otherwise. Uses the events of the UTC dates before, of and after the instant.
Palette paletteAt(const QDateTime& utc, double lat, double lon);

// Exposed for tests only.
namespace detail {
// Longitude wrapped into (-180, 180].
double wrapLongitude(double lon);
// First guess at the solar noon of UTC day `utcDay` (days since the Unix epoch), in Unix seconds:
// 12:00 UTC - lon/15 h with lon wrapped, so it always falls within that UTC day.
double noonGuess(double utcDay, double lon);
} // namespace detail
