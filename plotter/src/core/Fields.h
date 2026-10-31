#pragma once
#include "VesselState.h"
#include <QString>
#include <QStringView>
#include <optional>

enum class Field { Depth, Sog, Stw, Cog, Heading, WaterTemp, Position, Time, Rpm };
enum class DepthUnit { Feet, Metres, Fathoms };
enum class SpeedUnit { Knots, Mph, Kmh };
enum class TempUnit { F, C };

struct UnitPrefs {
    DepthUnit depth = DepthUnit::Feet;
    SpeedUnit speed = SpeedUnit::Knots;
    TempUnit temp = TempUnit::F;
    bool applyDepthOffset = true;
};

// Missing input renders as "--" (never a last-good value).
QString formatValue(Field, const VesselState&, const UnitPrefs&);
QString unitLabel(Field, const VesselState&, const UnitPrefs&);
// Stable identifiers used in JSON: depth sog stw cog hdg wtemp pos time rpm.
QString fieldName(Field);
std::optional<Field> fieldFromName(QStringView);
