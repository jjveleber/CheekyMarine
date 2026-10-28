#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace n2k {

struct AisTarget {
    uint32_t mmsi = 0;
    char aisClass = '?';  // 'A' or 'B'; set by the caller after upsert, '?' until then
    std::optional<double> lat, lon, sog, cog, heading;
    std::optional<std::string> name, callsign;
    std::optional<int64_t> shipType, navStatus;
    double lastSeen = 0;  // any message
    double posSeen = 0;   // last position report with a valid lat and lon; 0 = never
};

class AisTargets {
public:
    AisTarget& upsert(uint32_t mmsi, double now);  // creates with lastSeen = now, or returns existing with lastSeen = now
    const AisTarget* find(uint32_t mmsi) const;
    size_t expire(double now, double maxAgeSeconds = 600);  // returns count removed
    std::vector<const AisTarget*> all() const;              // sorted by mmsi

private:
    std::map<uint32_t, AisTarget> targets_;
};

}  // namespace n2k
