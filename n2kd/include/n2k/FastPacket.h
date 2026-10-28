#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <utility>
#include <vector>

#include "n2k/Frame.h"

namespace n2k {

struct N2kMessage {
    N2kHeader header;
    std::vector<uint8_t> payload;
    double timestamp;
};

class FastPacketAssembler {
public:
    explicit FastPacketAssembler(std::function<bool(uint32_t pgn)> isFastPacket);

    // Single-frame PGNs return immediately; fast-packet PGNs return on completion.
    std::optional<N2kMessage> push(const CanFrame& frame);
    // Drop partial messages whose first frame is older than now - maxAgeSeconds
    // or more than 1 s in the future.
    void expire(double now, double maxAgeSeconds = 1.0);
    size_t droppedIncomplete() const { return dropped_; }

private:
    struct Partial {
        N2kHeader header;
        std::vector<uint8_t> data;
        size_t total;
        uint8_t nextIndex;
        uint8_t sequence;  // 3-bit sequence id of frame 0; continuations must match
        double startTime;
    };

    std::function<bool(uint32_t)> isFast_;
    std::map<std::pair<uint8_t, uint32_t>, Partial> partials_;
    size_t dropped_ = 0;
};

}  // namespace n2k
