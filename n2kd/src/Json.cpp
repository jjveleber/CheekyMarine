#include "n2k/Json.h"

#include <string>

#include "n2k/StateMappers.h"
#include "n2k/Version.h"

namespace n2k {

namespace {

template <class T>
nlohmann::json agedValue(const Aged<T>& a, double now, double maxAge) {
    if (!a.fresh(now, maxAge)) return nullptr;
    return *a.value;
}

template <class T>
nlohmann::json optValue(const std::optional<T>& v) {
    if (!v) return nullptr;
    return *v;
}

}  // namespace

nlohmann::json vesselSnapshot(const VesselState& vs, double now) {
    nlohmann::json pos = nullptr;
    if (vs.position.fresh(now, kNavMaxAge)) {
        pos = {{"lat", vs.position.value->first}, {"lon", vs.position.value->second}};
    }
    // stw and rpm have no dedicated max-age constant; they share the navigation one.
    return {
        {"type", "vessel"},
        {"t", now},
        {"pos", pos},
        {"sog", agedValue(vs.sog, now, kNavMaxAge)},
        {"cog", agedValue(vs.cog, now, kNavMaxAge)},
        {"hdg", agedValue(vs.heading, now, kNavMaxAge)},
        {"hdgRef", agedValue(vs.headingReference, now, kNavMaxAge)},
        {"depth", agedValue(vs.depth, now, kDepthMaxAge)},
        {"depthOffset", agedValue(vs.depthOffset, now, kDepthMaxAge)},
        {"stw", agedValue(vs.stw, now, kNavMaxAge)},
        {"waterTemp", agedValue(vs.waterTemp, now, kEnvMaxAge)},
        {"gnssTime", agedValue(vs.gnssTime, now, kNavMaxAge)},
        {"sats", agedValue(vs.satellites, now, kNavMaxAge)},
        {"rpm", agedValue(vs.engineRpm, now, kNavMaxAge)},
    };
}

nlohmann::json aisSnapshot(const AisTargets& ais, double now) {
    nlohmann::json targets = nlohmann::json::array();
    for (const AisTarget* t : ais.all()) {
        targets.push_back({
            {"mmsi", t->mmsi},
            {"class", std::string(1, t->aisClass)},
            {"lat", optValue(t->lat)},
            {"lon", optValue(t->lon)},
            {"sog", optValue(t->sog)},
            {"cog", optValue(t->cog)},
            {"hdg", optValue(t->heading)},
            {"name", optValue(t->name)},
            {"callsign", optValue(t->callsign)},
            {"shipType", optValue(t->shipType)},
            {"navStatus", optValue(t->navStatus)},
            {"age", now - t->lastSeen},
        });
    }
    return {{"type", "ais"}, {"t", now}, {"targets", targets}};
}

nlohmann::json helloMessage() {
    return {{"type", "hello"}, {"schema", kSchemaVersion}, {"version", std::string(version())}};
}

}  // namespace n2k
