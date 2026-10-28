#pragma once
#include <cstddef>
#include <nlohmann/json.hpp>
#include <optional>

#include "n2k/AisTargets.h"
#include "n2k/VesselState.h"

namespace n2k {

constexpr int kSchemaVersion = 1;

nlohmann::json vesselSnapshot(const VesselState& vs, double now);  // stale or unset values serialize as null
// With maxTargets set and more targets known, publishes the maxTargets most recently
// seen (still sorted by mmsi) and adds "truncated": true and "total": <count>.
nlohmann::json aisSnapshot(const AisTargets& ais, double now, std::optional<size_t> maxTargets = std::nullopt);
nlohmann::json helloMessage();

}  // namespace n2k
