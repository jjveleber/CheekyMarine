#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

#include "n2k/Frame.h"

// Test helper: splits a payload into NMEA 2000 fast-packet CAN frames.
inline std::vector<n2k::CanFrame> encodeFastPacket(uint32_t canId, uint8_t seq,
                                                   const std::vector<uint8_t>& payload) {
    std::vector<n2k::CanFrame> frames;
    size_t pos = 0;
    uint8_t idx = 0;
    while (pos < payload.size() || idx == 0) {
        n2k::CanFrame f{canId, 8, {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}, 0.0};
        f.data[0] = static_cast<uint8_t>((seq << 5) | idx);
        size_t off = 1;
        if (idx == 0) {
            f.data[1] = static_cast<uint8_t>(payload.size());
            off = 2;
        }
        size_t n = std::min(payload.size() - pos, 8 - off);
        std::copy_n(payload.begin() + pos, n, f.data.begin() + off);
        pos += n;
        ++idx;
        frames.push_back(f);
    }
    return frames;
}
