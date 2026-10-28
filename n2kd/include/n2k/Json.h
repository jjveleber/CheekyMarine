#pragma once
#include <nlohmann/json.hpp>

#include "n2k/AisTargets.h"
#include "n2k/VesselState.h"

namespace n2k {

constexpr int kSchemaVersion = 1;

nlohmann::json vesselSnapshot(const VesselState& vs, double now);  // stale or unset values serialize as null
nlohmann::json aisSnapshot(const AisTargets& ais, double now);
nlohmann::json helloMessage();

}  // namespace n2k
