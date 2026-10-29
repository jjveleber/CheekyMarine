#pragma once
#include <utility>
#include <vector>

#include "n2k/PgnDatabase.h"
#include "n2k/PgnDecoder.h"

static const n2k::PgnDatabase& db() {
    static auto d = *n2k::PgnDatabase::load(N2K_CANBOAT_JSON);
    return d;
}
static n2k::N2kMessage msg(uint32_t id, std::vector<uint8_t> p, double t = 1.0) {
    return {n2k::parseHeader(id), std::move(p), t};
}
