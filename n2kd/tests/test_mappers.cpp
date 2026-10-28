#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "TestHelpers.h"
#include "n2k/AisTargets.h"
#include "n2k/StateMappers.h"
#include "n2k/VesselState.h"

TEST_CASE("position, cog/sog, heading, depth, temp land in VesselState") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(0x09F80123, {0x30,0x21,0x60,0x1C,0x58,0x9A,0x15,0xB7}, 10)), vs, ais);
    mp.apply(*dec.decode(msg(0x09F80223, {0x01,0xFC,0xE6,0x91,0x49,0x01,0xFF,0xFF}, 10)), vs, ais);
    mp.apply(*dec.decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0xFF,0x7F,0xFD}, 10)), vs, ais);
    mp.apply(*dec.decode(msg(0x0DF50B10, {0xFF,0xA2,0x05,0x00,0x00,0xD4,0xFE,0xFF}, 10)), vs, ais);
    mp.apply(*dec.decode(msg(0x15FD0610, {0x00,0x5D,0x70,0xFF,0xFF,0xFF,0xFF,0xFF}, 10)), vs, ais);
    REQUIRE(vs.position.value->first == Catch::Approx(47.6062)); REQUIRE(*vs.sog.value == Catch::Approx(3.29));
    REQUIRE(*vs.cog.value == Catch::Approx(3.7350)); REQUIRE(*vs.heading.value == Catch::Approx(3.6739));
    REQUIRE(*vs.headingReference.value == "Magnetic");
    REQUIRE(*vs.depth.value == Catch::Approx(14.42)); REQUIRE(*vs.depthOffset.value == Catch::Approx(-0.3));
    REQUIRE(*vs.waterTemp.value == Catch::Approx(287.65)); REQUIRE(vs.position.updatedAt == 10);
}
TEST_CASE("magnetic COG is ignored") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(0x09F80223, {0x01,0xFD,0xE6,0x91,0x49,0x01,0xFF,0xFF}, 10)), vs, ais); // cogReference = 1 Magnetic
    REQUIRE_FALSE(vs.cog.value); REQUIRE(*vs.sog.value == Catch::Approx(3.29));
}
TEST_CASE("not-available depth leaves previous depth but does not refresh it") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(0x0DF50B10, {0xFF,0xA2,0x05,0x00,0x00,0xD4,0xFE,0xFF}, 10)), vs, ais);
    mp.apply(*dec.decode(msg(0x0DF50B10, {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x7F,0xFF}, 20)), vs, ais);
    REQUIRE(*vs.depth.value == Catch::Approx(14.42)); REQUIRE(vs.depth.updatedAt == 10);
    REQUIRE_FALSE(vs.depth.fresh(20, n2k::kDepthMaxAge));
}
TEST_CASE("GPS dropout: nav values go stale after 5 s, depth has its own clock") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(0x09F80123, {0x30,0x21,0x60,0x1C,0x58,0x9A,0x15,0xB7}, 100)), vs, ais);
    mp.apply(*dec.decode(msg(0x0DF50B10, {0xFF,0xA2,0x05,0x00,0x00,0xD4,0xFE,0xFF}, 104)), vs, ais);
    REQUIRE_FALSE(vs.position.fresh(105.1, n2k::kNavMaxAge)); REQUIRE(vs.depth.fresh(105.1, n2k::kDepthMaxAge));
}
TEST_CASE("AIS class A position creates a target") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p = {0x01, 0xFA,0xDB,0xE1,0x15, 0x00,0x3E,0x0B,0xB7, 0x40,0x71,0x6E,0x1C, 0x00, 0xE6,0x91, 0x49,0x01, 0x00,0x00,0x00, 0x83,0x8F, 0xFF,0x7F, 0xF0, 0xFF, 0xFF};
    mp.apply(*dec.decode(msg(0x11F80E30, p, 50)), vs, ais);
    auto* t = ais.find(367123450); REQUIRE(t); REQUIRE(t->aisClass == 'A');
    REQUIRE(*t->lat == Catch::Approx(47.70)); REQUIRE(*t->sog == Catch::Approx(3.29)); REQUIRE(t->lastSeen == 50);
}

static void putLe(std::vector<uint8_t>& p, size_t off, uint32_t v, int bytes) {
    for (int i = 0; i < bytes; ++i) p[off + i] = static_cast<uint8_t>(v >> (8 * i));
}
static void putStr(std::vector<uint8_t>& p, size_t off, const char* s) {
    for (size_t i = 0; s[i]; ++i) p[off + i] = static_cast<uint8_t>(s[i]);
}

TEST_CASE("AIS class A static data 129794 sets name, callsign, shipType") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p(76, 0xFF);
    p[0] = 0x05; putLe(p, 1, 367123450, 4);
    putStr(p, 9, "WDE1234"); putStr(p, 16, "ARGOSY");
    for (size_t i = 22; i < 36; ++i) p[i] = '@';
    p[36] = 70;
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129794, 0x30), p, 60)), vs, ais);
    auto* t = ais.find(367123450); REQUIRE(t);
    REQUIRE(t->aisClass == 'A');
    REQUIRE(*t->name == "ARGOSY"); REQUIRE(*t->callsign == "WDE1234"); REQUIRE(*t->shipType == 70);
    REQUIRE(t->lastSeen == 60);
}
TEST_CASE("AIS class B position 129039 creates a class B target") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p(27, 0xFF);
    p[0] = 0x12; putLe(p, 1, 338123456, 4);
    putLe(p, 5, static_cast<uint32_t>(-1224000000), 4);  // lon -122.40
    putLe(p, 9, 477000000, 4);                           // lat 47.70
    putLe(p, 14, 12345, 2);                              // cog 1.2345 rad
    putLe(p, 16, 250, 2);                                // sog 2.50 m/s
    putLe(p, 21, 0xFFFF, 2);                             // heading n/a
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129039, 0x31), p, 70)), vs, ais);
    auto* t = ais.find(338123456); REQUIRE(t);
    REQUIRE(t->aisClass == 'B');
    REQUIRE(*t->lon == Catch::Approx(-122.40)); REQUIRE(*t->lat == Catch::Approx(47.70));
    REQUIRE(*t->sog == Catch::Approx(2.50)); REQUIRE(*t->cog == Catch::Approx(1.2345));
    REQUIRE_FALSE(t->heading);
}

TEST_CASE("AIS position report with lat/lon not available clears the old position and keeps posSeen") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p = {0x01, 0xFA,0xDB,0xE1,0x15, 0x00,0x3E,0x0B,0xB7, 0x40,0x71,0x6E,0x1C, 0x00, 0xE6,0x91, 0x49,0x01, 0x00,0x00,0x00, 0x83,0x8F, 0xFF,0x7F, 0xF0, 0xFF, 0xFF};
    mp.apply(*dec.decode(msg(0x11F80E30, p, 50)), vs, ais);
    REQUIRE(ais.find(367123450)->posSeen == 50);
    putLe(p, 5, 0x7FFFFFFF, 4); putLe(p, 9, 0x7FFFFFFF, 4);   // lon, lat not available
    putLe(p, 14, 0xFFFF, 2); putLe(p, 16, 0xFFFF, 2);        // cog, sog not available
    mp.apply(*dec.decode(msg(0x11F80E30, p, 80)), vs, ais);
    auto* t = ais.find(367123450); REQUIRE(t);
    REQUIRE_FALSE(t->lat); REQUIRE_FALSE(t->lon); REQUIRE_FALSE(t->sog); REQUIRE_FALSE(t->cog);
    REQUIRE(t->lastSeen == 80); REQUIRE(t->posSeen == 50);
}
TEST_CASE("AIS static data does not touch posSeen") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> pos = {0x01, 0xFA,0xDB,0xE1,0x15, 0x00,0x3E,0x0B,0xB7, 0x40,0x71,0x6E,0x1C, 0x00, 0xE6,0x91, 0x49,0x01, 0x00,0x00,0x00, 0x83,0x8F, 0xFF,0x7F, 0xF0, 0xFF, 0xFF};
    mp.apply(*dec.decode(msg(0x11F80E30, pos, 50)), vs, ais);
    std::vector<uint8_t> p(76, 0xFF);
    p[0] = 0x05; putLe(p, 1, 367123450, 4);
    putStr(p, 9, "WDE1234"); putStr(p, 16, "ARGOSY");
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129794, 0x30), p, 60)), vs, ais);
    auto* t = ais.find(367123450); REQUIRE(t);
    REQUIRE(t->lastSeen == 60); REQUIRE(t->posSeen == 50); REQUIRE(*t->lat == Catch::Approx(47.70));
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129794, 0x32), [] {
        std::vector<uint8_t> q(76, 0xFF); q[0] = 0x05; putLe(q, 1, 316000001, 4); return q; }(), 61)), vs, ais);
    REQUIRE(ais.find(316000001)->posSeen == 0);
}
