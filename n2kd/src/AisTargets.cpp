#include "n2k/AisTargets.h"

namespace n2k {

AisTarget& AisTargets::upsert(uint32_t mmsi, double now) {
    auto [it, inserted] = targets_.try_emplace(mmsi);
    if (inserted) it->second.mmsi = mmsi;
    it->second.lastSeen = now;
    return it->second;
}

const AisTarget* AisTargets::find(uint32_t mmsi) const {
    auto it = targets_.find(mmsi);
    return it == targets_.end() ? nullptr : &it->second;
}

size_t AisTargets::expire(double now, double maxAgeSeconds) {
    size_t removed = 0;
    for (auto it = targets_.begin(); it != targets_.end();) {
        const double age = now - it->second.lastSeen;
        if (age > maxAgeSeconds || age < -1.0) {  // more than 1 s in the future also expires
            it = targets_.erase(it);
            ++removed;
        } else {
            ++it;
        }
    }
    return removed;
}

std::vector<const AisTarget*> AisTargets::all() const {
    std::vector<const AisTarget*> out;
    out.reserve(targets_.size());
    for (const auto& [mmsi, target] : targets_) out.push_back(&target);
    return out;
}

}  // namespace n2k
