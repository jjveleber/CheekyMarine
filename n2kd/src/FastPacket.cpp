#include "n2k/FastPacket.h"

#include <algorithm>

namespace n2k {

namespace {
constexpr size_t kMaxFastPacketLength = 223;  // 32 frames: 6 + 31 * 7 bytes
}

FastPacketAssembler::FastPacketAssembler(std::function<bool(uint32_t pgn)> isFastPacket)
    : isFast_(std::move(isFastPacket)) {}

std::optional<N2kMessage> FastPacketAssembler::push(const CanFrame& frame) {
    N2kHeader h = parseHeader(frame.id);
    const size_t len = std::min<size_t>(frame.len, frame.data.size());

    if (!isFast_(h.pgn)) {
        return N2kMessage{h, std::vector<uint8_t>(frame.data.begin(), frame.data.begin() + len),
                          frame.timestamp};
    }
    if (len < 1) return std::nullopt;

    const auto key = std::make_pair(h.source, h.pgn);
    const uint8_t index = frame.data[0] & 0x1F;
    const uint8_t sequence = frame.data[0] >> 5;
    auto it = partials_.find(key);

    if (index == 0) {
        // Frame 0 restarts the key. A discarded unfinished partial counts as dropped.
        if (it != partials_.end()) {
            ++dropped_;
            partials_.erase(it);
        }
        if (len < 2) return std::nullopt;
        const size_t total = frame.data[1];
        if (total == 0 || total > kMaxFastPacketLength) return std::nullopt;
        Partial p{h, {}, total, 1, sequence, frame.timestamp};
        p.data.insert(p.data.end(), frame.data.begin() + 2, frame.data.begin() + len);
        partials_.emplace(key, std::move(p));
        it = partials_.find(key);
    } else {
        if (it == partials_.end()) return std::nullopt;  // no partial: ignore, not counted
        // A wrong index or another message's sequence id means frames were lost.
        if (index != it->second.nextIndex || sequence != it->second.sequence) {
            ++dropped_;
            partials_.erase(it);
            return std::nullopt;
        }
        it->second.data.insert(it->second.data.end(), frame.data.begin() + 1,
                               frame.data.begin() + len);
        ++it->second.nextIndex;
    }

    Partial& p = it->second;
    if (p.data.size() < p.total) return std::nullopt;
    p.data.resize(p.total);
    // Message timestamp is that of the completing frame.
    N2kMessage msg{p.header, std::move(p.data), frame.timestamp};
    partials_.erase(it);
    return msg;
}

void FastPacketAssembler::expire(double now, double maxAgeSeconds) {
    for (auto it = partials_.begin(); it != partials_.end();) {
        const double start = it->second.startTime;
        if (start < now - maxAgeSeconds || start > now + 1.0) {  // more than 1 s in the future also expires
            ++dropped_;
            it = partials_.erase(it);
        } else {
            ++it;
        }
    }
}

}  // namespace n2k
