#include "n2k/StateMappers.h"

namespace n2k {
namespace {

std::optional<double> getD(const DecodedMessage& m, const char* id) {
    auto it = m.fields.find(id);
    if (it == m.fields.end()) return std::nullopt;
    if (auto* d = std::get_if<double>(&it->second)) return *d;
    if (auto* i = std::get_if<int64_t>(&it->second)) return static_cast<double>(*i);
    return std::nullopt;
}
std::optional<int64_t> getI(const DecodedMessage& m, const char* id) {
    auto it = m.fields.find(id);
    if (it == m.fields.end()) return std::nullopt;
    if (auto* i = std::get_if<int64_t>(&it->second)) return *i;
    return std::nullopt;
}
std::optional<std::string> getS(const DecodedMessage& m, const char* id) {
    auto it = m.fields.find(id);
    if (it == m.fields.end()) return std::nullopt;
    if (auto* s = std::get_if<std::string>(&it->second)) return *s;
    return std::nullopt;
}

void setPosition(const DecodedMessage& m, VesselState& vs) {
    auto lat = getD(m, "latitude"), lon = getD(m, "longitude");
    if (lat && lon) vs.position.set({*lat, *lon}, m.timestamp);
}
void setGnssTime(const DecodedMessage& m, VesselState& vs) {
    auto date = getD(m, "date"), time = getD(m, "time");
    if (date && time) vs.gnssTime.set(*date * 86400.0 + *time, m.timestamp);
}
void setIf(Aged<double>& a, const std::optional<double>& v, double now) {
    if (v) a.set(*v, now);
}
template <class T> void assignIf(std::optional<T>& dst, const std::optional<T>& v) {
    if (v) dst = v;
}

// Reports of our own transponder (transceiver information 2 or 3: own VDL transmission,
// 4: own information not broadcast) are not targets: nullptr, nothing touched.
AisTarget* aisTarget(const DecodedMessage& m, AisTargets& ais, char cls) {
    auto xcvr = getI(m, "aisTransceiverInformation");
    if (xcvr && *xcvr >= 2 && *xcvr <= 4) return nullptr;
    auto id = getI(m, "userId");
    if (!id) return nullptr;
    AisTarget& t = ais.upsert(static_cast<uint32_t>(*id), m.timestamp);
    t.aisClass = cls;
    return &t;
}
// A position report is authoritative: a field it marks not available clears the old value.
void aisKinematics(const DecodedMessage& m, AisTarget& t) {
    t.lon = getD(m, "longitude");
    t.lat = getD(m, "latitude");
    t.sog = getD(m, "sog");
    t.cog = getD(m, "cog");
    t.heading = getD(m, "heading");
    if (t.lat && t.lon) t.posSeen = m.timestamp;
}

}  // namespace

bool StateMappers::accept(Group g, const DecodedMessage& m, double maxAge) {
    SourceLock& l = locks_[g];
    const double now = m.timestamp;
    // Silent: nothing from the locked source within maxAge (a stamp more than 1 s in
    // the future, after a clock step back, also counts as silent).
    const bool silent = !l.source || now - l.lastSeen > maxAge || now < l.lastSeen - 1.0;
    if (l.source != m.source && !silent) return false;
    l.source = m.source;
    l.lastSeen = now;
    return true;
}

void StateMappers::apply(const DecodedMessage& m, VesselState& vs, AisTargets& ais) {
    const double now = m.timestamp;
    switch (m.pgn) {
    case 129025:
        if (accept(kPosition, m, kNavMaxAge)) setPosition(m, vs);
        break;
    case 129026:
        if (!accept(kCogSog, m, kNavMaxAge)) break;
        setIf(vs.sog, getD(m, "sog"), now);
        if (getI(m, "cogReference") == 0) setIf(vs.cog, getD(m, "cog"), now);
        break;
    case 129029:
        if (accept(kPosition, m, kNavMaxAge)) {
            setPosition(m, vs);
            if (auto n = getI(m, "numberOfSvs")) vs.satellites.set(*n, now);
        }
        if (accept(kGnssTime, m, kNavMaxAge)) setGnssTime(m, vs);
        break;
    case 126992:
        if (accept(kGnssTime, m, kNavMaxAge)) setGnssTime(m, vs);
        break;
    case 127250:
    {
        if (!accept(kHeading, m, kNavMaxAge)) break;
        // Only True (0) or Magnetic (1) headings are usable; Error or n/a clears both.
        const auto ref = getI(m, "reference");
        if (ref == 0 || ref == 1) {
            setIf(vs.heading, getD(m, "heading"), now);
            if (auto r = getS(m, "referenceName")) vs.headingReference.set(*r, now);
        } else {
            vs.heading = Aged<double>{};
            vs.headingReference = Aged<std::string>{};
        }
        if (auto v = getD(m, "variation")) {
            vs.variation.set(*v, now);
            headingVariation_.set(*v, now);
        }
        break;
    }
    case 127258:
        if (!headingVariation_.fresh(now, kNavMaxAge)) setIf(vs.variation, getD(m, "variation"), now);
        break;
    case 128267:
        // Depth and offset come from the same message: an offset marked not available
        // clears the previous one rather than pairing it with this depth.
        if (!accept(kDepth, m, kDepthMaxAge)) break;
        setIf(vs.depth, getD(m, "depth"), now);
        if (auto o = getD(m, "offset")) {
            vs.depthOffset.set(*o, now);
        } else {
            vs.depthOffset = Aged<double>{};
        }
        break;
    case 128259:
        if (accept(kStw, m, kNavMaxAge)) setIf(vs.stw, getD(m, "speedWaterReferenced"), now);
        break;
    case 130310:
        if (accept(kWaterTemp, m, kEnvMaxAge)) setIf(vs.waterTemp, getD(m, "waterTemperature"), now);
        break;
    case 130311:
        if (getI(m, "temperatureSource") == 0 && accept(kWaterTemp, m, kEnvMaxAge)) {
            setIf(vs.waterTemp, getD(m, "temperature"), now);
        }
        break;
    case 130316:
        if (getI(m, "source") == 0 && accept(kWaterTemp, m, kEnvMaxAge)) setIf(vs.waterTemp, getD(m, "temperature"), now);
        break;
    case 127488:
        if (getI(m, "instance") == 0 && accept(kRpm, m, kNavMaxAge)) setIf(vs.engineRpm, getD(m, "speed"), now);
        break;
    case 129038:
        if (auto* t = aisTarget(m, ais, 'A')) {
            aisKinematics(m, *t);
            t->navStatus = getI(m, "navStatus");
        }
        break;
    case 129039:
        if (auto* t = aisTarget(m, ais, 'B')) aisKinematics(m, *t);
        break;
    case 129794:
        if (auto* t = aisTarget(m, ais, 'A')) {
            assignIf(t->name, getS(m, "name"));
            assignIf(t->callsign, getS(m, "callsign"));
            assignIf(t->shipType, getI(m, "typeOfShip"));
        }
        break;
    case 129809:
        if (auto* t = aisTarget(m, ais, 'B')) assignIf(t->name, getS(m, "name"));
        break;
    case 129810:
        if (auto* t = aisTarget(m, ais, 'B')) {
            assignIf(t->callsign, getS(m, "callsign"));
            assignIf(t->shipType, getI(m, "typeOfShip"));
        }
        break;
    default:
        break;
    }
}

}  // namespace n2k
