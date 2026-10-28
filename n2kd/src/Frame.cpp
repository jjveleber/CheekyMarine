#include "n2k/Frame.h"

namespace n2k {

N2kHeader parseHeader(uint32_t canId) {
    const auto priority = static_cast<uint8_t>((canId >> 26) & 0x7);
    const uint32_t dp = (canId >> 24) & 0x1;
    const uint32_t pf = (canId >> 16) & 0xFF;
    const uint32_t ps = (canId >> 8) & 0xFF;
    const auto source = static_cast<uint8_t>(canId & 0xFF);

    if (pf < 240) {
        return {priority, (dp << 16) | (pf << 8), source, static_cast<uint8_t>(ps)};
    }
    return {priority, (dp << 16) | (pf << 8) | ps, source, 255};
}

uint32_t makeCanId(uint8_t priority, uint32_t pgn, uint8_t source, uint8_t destination) {
    const uint32_t dp = (pgn >> 16) & 0x1;
    const uint32_t pf = (pgn >> 8) & 0xFF;
    const uint32_t ps = (pf < 240) ? destination : (pgn & 0xFF);
    return (static_cast<uint32_t>(priority & 0x7) << 26) | (dp << 24) | (pf << 16) | (ps << 8) |
           source;
}

}  // namespace n2k
