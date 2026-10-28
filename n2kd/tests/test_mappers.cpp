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

TEST_CASE("own-ship AIS reports (transceiver information 2, 3 or 4) do not create or touch targets") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    // 129039 with aisTransceiverInformation (bits 163-167) = 2, Channel A VDL transmission.
    std::vector<uint8_t> b(27, 0xFF);
    b[0] = 0x12; putLe(b, 1, 338000009, 4); putLe(b, 5, static_cast<uint32_t>(-1224000000), 4); putLe(b, 9, 477000000, 4);
    b[20] = static_cast<uint8_t>((b[20] & 0x07) | (2 << 3));
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129039, 0x31), b, 70)), vs, ais);
    REQUIRE_FALSE(ais.find(338000009));
    // 129794 with transceiver information (bits 592-596) = 4, own information not broadcast.
    std::vector<uint8_t> s(76, 0xFF);
    s[0] = 0x05; putLe(s, 1, 338000009, 4); putStr(s, 16, "OWNSHIP");
    s[74] = static_cast<uint8_t>((s[74] & 0xE0) | 4);
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 129794, 0x31), s, 71)), vs, ais);
    REQUIRE_FALSE(ais.find(338000009));
    // An existing target is not touched by a 129038 own report (transceiver 3) with its MMSI.
    std::vector<uint8_t> a = {0x01, 0xFA,0xDB,0xE1,0x15, 0x00,0x3E,0x0B,0xB7, 0x40,0x71,0x6E,0x1C, 0x00, 0xE6,0x91, 0x49,0x01, 0x00,0x00,0x00, 0x83,0x8F, 0xFF,0x7F, 0xF0, 0xFF, 0xFF};
    mp.apply(*dec.decode(msg(0x11F80E30, a, 50)), vs, ais);
    REQUIRE(ais.find(367123450));
    a[20] = static_cast<uint8_t>((a[20] & 0x07) | (3 << 3));
    putLe(a, 9, 400000000, 4);  // lat 40.0
    mp.apply(*dec.decode(msg(0x11F80E30, a, 60)), vs, ais);
    auto* t = ais.find(367123450); REQUIRE(t);
    REQUIRE(*t->lat == Catch::Approx(47.70)); REQUIRE(t->lastSeen == 50);
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

// 128267 from source src: depth (0.01 m), offset (0.001 m, 0x7FFF = not available).
static n2k::N2kMessage depthMsg(uint8_t src, uint32_t depthCm, uint16_t offsetMm, double t) {
    std::vector<uint8_t> p(8, 0xFF);
    putLe(p, 1, depthCm, 4); putLe(p, 5, offsetMm, 2);
    return msg(n2k::makeCanId(3, 128267, src), p, t);
}

TEST_CASE("two depth sounders: the first source is locked and its depth and offset stay paired") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    for (double t = 10; t < 13; t += 0.5) {
        mp.apply(*dec.decode(depthMsg(35, 1000, 500, t)), vs, ais);           // 10.0 m, offset +0.5
        mp.apply(*dec.decode(depthMsg(36, 300, 0x7FFF, t + 0.25)), vs, ais);  // 3.0 m, offset n/a
        REQUIRE(*vs.depth.value == Catch::Approx(10.0));
        REQUIRE(*vs.depthOffset.value == Catch::Approx(0.5));
    }
    // Source 35 last spoke at 12.5; within kDepthMaxAge source 36 is still ignored.
    mp.apply(*dec.decode(depthMsg(36, 300, 0x7FFF, 12.5 + n2k::kDepthMaxAge)), vs, ais);
    REQUIRE(*vs.depth.value == Catch::Approx(10.0));
    // Silent for longer than kDepthMaxAge: source 36 takes the lock; its n/a offset clears the old one.
    mp.apply(*dec.decode(depthMsg(36, 300, 0x7FFF, 12.6 + n2k::kDepthMaxAge)), vs, ais);
    REQUIRE(*vs.depth.value == Catch::Approx(3.0));
    REQUIRE_FALSE(vs.depthOffset.value);
    // Source 35 is back but 36 now holds the lock.
    mp.apply(*dec.decode(depthMsg(35, 1000, 500, 13 + n2k::kDepthMaxAge)), vs, ais);
    REQUIRE(*vs.depth.value == Catch::Approx(3.0));
}
TEST_CASE("depth offset not available in a 128267 clears the previous offset") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(depthMsg(35, 1000, 500, 10)), vs, ais);
    REQUIRE(*vs.depthOffset.value == Catch::Approx(0.5));
    mp.apply(*dec.decode(depthMsg(35, 1100, 0x7FFF, 11)), vs, ais);
    REQUIRE(*vs.depth.value == Catch::Approx(11.0));
    REQUIRE_FALSE(vs.depthOffset.value);
}
TEST_CASE("127250 variation fills VesselState variation and wins over 127258") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    // heading 3.6739, deviation n/a, variation +0.2618 rad (15 deg east), reference Magnetic.
    mp.apply(*dec.decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0x3A,0x0A,0xFD}, 10)), vs, ais);
    REQUIRE(*vs.variation.value == Catch::Approx(0.2618)); REQUIRE(vs.variation.updatedAt == 10);
    // 127258 while 127250 variation is fresh: ignored.
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 127258, 0x05), {0x00,0xF1,0xFF,0xFF,0xC6,0xF5,0xFF,0xFF}, 11)), vs, ais);
    REQUIRE(*vs.variation.value == Catch::Approx(0.2618));
    // Once the 127250 variation is older than kNavMaxAge, 127258 supplies it.
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 127258, 0x05), {0x00,0xF1,0xFF,0xFF,0xC6,0xF5,0xFF,0xFF}, 16)), vs, ais);
    REQUIRE(*vs.variation.value == Catch::Approx(-0.2618)); REQUIRE(vs.variation.updatedAt == 16);
}
TEST_CASE("127258 alone fills variation; 127250 with variation n/a does not clear it") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 127258, 0x05), {0x00,0xF1,0xFF,0xFF,0x3A,0x0A,0xFF,0xFF}, 10)), vs, ais);
    REQUIRE(*vs.variation.value == Catch::Approx(0.2618));
    mp.apply(*dec.decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0xFF,0x7F,0xFD}, 10.5)), vs, ais);
    mp.apply(*dec.decode(msg(n2k::makeCanId(7, 127258, 0x05), {0x00,0xF1,0xFF,0xFF,0x3B,0x0A,0xFF,0xFF}, 11)), vs, ais);
    REQUIRE(*vs.variation.value == Catch::Approx(0.2619)); REQUIRE(vs.variation.updatedAt == 11);
}
TEST_CASE("127250 with reference Error drops heading and reference") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0xFF,0x7F,0xFD}, 9)), vs, ais);    // Magnetic
    REQUIRE(vs.heading.value);
    mp.apply(*dec.decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0xFF,0x7F,0xFE}, 10)), vs, ais);  // reference 2
    REQUIRE_FALSE(vs.heading.value); REQUIRE_FALSE(vs.headingReference.value);
}
TEST_CASE("two GPS sources: position stays on the first source") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> a(8), b(8);
    putLe(a, 0, 476062000, 4); putLe(a, 4, static_cast<uint32_t>(-1223321000), 4);
    putLe(b, 0, 480000000, 4); putLe(b, 4, static_cast<uint32_t>(-1230000000), 4);
    mp.apply(*dec.decode(msg(n2k::makeCanId(2, 129025, 0x10), a, 10)), vs, ais);
    mp.apply(*dec.decode(msg(n2k::makeCanId(2, 129025, 0x11), b, 10.1)), vs, ais);
    REQUIRE(vs.position.value->first == Catch::Approx(47.6062));
    REQUIRE(vs.position.updatedAt == 10);
}

TEST_CASE("127488 engine speed only from instance 0") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(n2k::makeCanId(2, 127488, 0x40), {0x01,0x40,0x1F,0xFF,0xFF,0x7F,0xFF,0xFF}, 10)), vs, ais);
    REQUIRE_FALSE(vs.engineRpm.value);  // instance 1 ignored
    mp.apply(*dec.decode(msg(n2k::makeCanId(2, 127488, 0x40), {0x00,0x40,0x1F,0xFF,0xFF,0x7F,0xFF,0xFF}, 11)), vs, ais);
    REQUIRE(*vs.engineRpm.value == Catch::Approx(2000.0)); REQUIRE(vs.engineRpm.updatedAt == 11);
}
TEST_CASE("130310 water temperature") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    mp.apply(*dec.decode(msg(n2k::makeCanId(5, 130310, 0x23), {0x00,0x5D,0x70,0xFF,0xFF,0xFF,0xFF,0xFF}, 10)), vs, ais);
    REQUIRE(*vs.waterTemp.value == Catch::Approx(287.65));
}
TEST_CASE("130316 temperature only from source 0 (sea temperature)") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    // 288.150 K; source 1 (outside temperature) is ignored and does not take the lock.
    mp.apply(*dec.decode(msg(n2k::makeCanId(5, 130316, 0x23), {0x00,0x00,0x01,0x96,0x65,0x04,0xFF,0xFF}, 10)), vs, ais);
    REQUIRE_FALSE(vs.waterTemp.value);
    mp.apply(*dec.decode(msg(n2k::makeCanId(5, 130316, 0x24), {0x00,0x00,0x00,0x96,0x65,0x04,0xFF,0xFF}, 11)), vs, ais);
    REQUIRE(*vs.waterTemp.value == Catch::Approx(288.15));
}
TEST_CASE("AIS class B static data 129810 sets callsign and shipType") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p(35, 0xFF);
    p[0] = 0x18; putLe(p, 1, 338123456, 4);
    p[5] = 37;                   // typeOfShip: pleasure craft
    putStr(p, 13, "WDF5678");    // callsign, bytes 13-19
    mp.apply(*dec.decode(msg(n2k::makeCanId(6, 129810, 0x31), p, 80)), vs, ais);
    auto* t = ais.find(338123456); REQUIRE(t);
    REQUIRE(t->aisClass == 'B');
    REQUIRE(*t->callsign == "WDF5678"); REQUIRE(*t->shipType == 37); REQUIRE(t->lastSeen == 80);
}
TEST_CASE("126992 system time sets gnssTime") {
    n2k::VesselState vs; n2k::AisTargets ais; n2k::PgnDecoder dec(db()); n2k::StateMappers mp;
    std::vector<uint8_t> p(8, 0xFF);
    p[0] = 0x00; p[1] = 0xF0;    // sid, source GPS
    putLe(p, 2, 19700, 2);       // days since 1970-01-01
    putLe(p, 4, 36005000, 4);    // 3600.5 s, 0.0001 s units
    mp.apply(*dec.decode(msg(n2k::makeCanId(3, 126992, 0x00), p, 12)), vs, ais);
    REQUIRE(*vs.gnssTime.value == Catch::Approx(19700.0 * 86400 + 3600.5)); REQUIRE(vs.gnssTime.updatedAt == 12);
}
