#pragma once
#include <array>
#include <cstdint>

namespace n2k {

struct CanFrame {
    uint32_t id;
    uint8_t len;
    std::array<uint8_t, 8> data;
    double timestamp;  // seconds since epoch, 0 if unknown
};

struct N2kHeader {
    uint8_t priority;
    uint32_t pgn;
    uint8_t source;
    uint8_t destination;  // 255 = broadcast (PDU2)
};

N2kHeader parseHeader(uint32_t canId);
uint32_t makeCanId(uint8_t priority, uint32_t pgn, uint8_t source, uint8_t destination = 255);

}  // namespace n2k
