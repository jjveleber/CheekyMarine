#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <optional>

#include "n2k/AisTargets.h"
#include "n2k/PgnDecoder.h"
#include "n2k/VesselState.h"

namespace n2k {

constexpr double kNavMaxAge = 5.0;    // s: position, sog, cog, heading, gnssTime
constexpr double kDepthMaxAge = 5.0;  // s
constexpr double kEnvMaxAge = 30.0;   // s: waterTemp

// Maps decoded PGNs onto VesselState and AisTargets. Each vessel quantity group is
// locked to the first source address seen; other sources are ignored until the
// locked one has been silent for longer than the group's max age, after which the
// next message from any source takes the lock. Silent means no message with an
// available primary value (depth only for depth, heading only for heading).
class StateMappers {
public:
    void apply(const DecodedMessage& m, VesselState& vs, AisTargets& ais);

private:
    // position: 129025, 129029 (and satellites); cogSog: 129026; heading: 127250;
    // depth: 128267; stw: 128259; waterTemp: 130310, 130311, 130316;
    // gnssTime: 126992, 129029; rpm: 127488.
    enum Group : size_t { kPosition, kCogSog, kHeading, kDepth, kStw, kWaterTemp, kGnssTime, kRpm, kGroupCount };
    struct SourceLock {
        std::optional<uint8_t> source;
        double lastSeen = 0;
    };
    // True if m may update group g. Only a message with at least one available value
    // among `fields` (the group's primary values) takes or refreshes the lock.
    bool accept(Group g, const DecodedMessage& m, double maxAge, std::initializer_list<const char*> fields);

    std::array<SourceLock, kGroupCount> locks_{};
    Aged<double> headingVariation_;  // last 127250 variation; while fresh, 127258 is ignored
};

}  // namespace n2k
