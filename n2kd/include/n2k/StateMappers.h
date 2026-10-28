#pragma once
#include "n2k/AisTargets.h"
#include "n2k/PgnDecoder.h"
#include "n2k/VesselState.h"

namespace n2k {

constexpr double kNavMaxAge = 5.0;    // s: position, sog, cog, heading, gnssTime
constexpr double kDepthMaxAge = 5.0;  // s
constexpr double kEnvMaxAge = 30.0;   // s: waterTemp

class StateMappers {
public:
    void apply(const DecodedMessage& m, VesselState& vs, AisTargets& ais) const;
};

}  // namespace n2k
