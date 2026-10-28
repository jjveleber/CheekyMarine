#include <catch2/catch_test_macros.hpp>
#include <numeric>

#include "FastPacketEncoder.h"
#include "n2k/FastPacket.h"

TEST_CASE("single-frame PGN passes straight through") {
    n2k::FastPacketAssembler fa([](uint32_t) { return false; });
    auto m = fa.push({0x0DF50B10, 8, {0xFF, 0xA2, 0x05, 0x00, 0x00, 0xD4, 0xFE, 0xFF}, 5.0});
    REQUIRE(m);
    REQUIRE(m->header.pgn == 128267);
    REQUIRE(m->payload.size() == 8);
    REQUIRE(m->payload[1] == 0xA2);
}
TEST_CASE("28-byte AIS payload reassembles from 5 frames") {
    std::vector<uint8_t> payload(28);
    std::iota(payload.begin(), payload.end(), 1);
    auto frames = encodeFastPacket(0x11F80E30, 3, payload);
    REQUIRE(frames.size() == 5);
    n2k::FastPacketAssembler fa([](uint32_t p) { return p == 129038; });
    for (size_t i = 0; i + 1 < frames.size(); ++i) REQUIRE_FALSE(fa.push(frames[i]));
    auto m = fa.push(frames.back());
    REQUIRE(m);
    REQUIRE(m->payload == payload);
    REQUIRE(m->header.source == 0x30);
}
TEST_CASE("two sources interleaving the same PGN do not mix") {
    std::vector<uint8_t> pa(28, 0xAA), pb(28, 0xBB);
    auto fa_ = encodeFastPacket(0x11F80E30, 0, pa);
    auto fb = encodeFastPacket(0x11F80E31, 0, pb);
    n2k::FastPacketAssembler fa([](uint32_t) { return true; });
    std::vector<n2k::N2kMessage> out;
    for (size_t i = 0; i < 5; ++i) {
        if (auto m = fa.push(fa_[i])) out.push_back(*m);
        if (auto m = fa.push(fb[i])) out.push_back(*m);
    }
    REQUIRE(out.size() == 2);
    REQUIRE(out[0].payload == pa);
    REQUIRE(out[1].payload == pb);
}
TEST_CASE("missing frame drops the partial and counts it") {
    std::vector<uint8_t> p(28, 1);
    auto fr = encodeFastPacket(0x11F80E30, 0, p);
    n2k::FastPacketAssembler fa([](uint32_t) { return true; });
    fa.push(fr[0]);
    fa.push(fr[1]); /* skip fr[2] */
    REQUIRE_FALSE(fa.push(fr[3]));
    REQUIRE_FALSE(fa.push(fr[4]));
    REQUIRE(fa.droppedIncomplete() == 1);
}
TEST_CASE("stale partial expires") {
    std::vector<uint8_t> p(28, 1);
    auto fr = encodeFastPacket(0x11F80E30, 0, p);
    n2k::FastPacketAssembler fa([](uint32_t) { return true; });
    fr[0].timestamp = 10.0;
    fa.push(fr[0]);
    fa.expire(12.0);
    REQUIRE(fa.droppedIncomplete() == 1);
}
