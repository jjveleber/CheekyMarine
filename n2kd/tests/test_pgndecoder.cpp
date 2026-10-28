#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "n2k/PgnDatabase.h"
#include "n2k/PgnDecoder.h"

static const n2k::PgnDatabase& db() {
    static auto d = *n2k::PgnDatabase::load(N2K_CANBOAT_JSON);
    return d;
}
static n2k::N2kMessage msg(uint32_t id, std::vector<uint8_t> p, double t = 1.0) {
    return {n2k::parseHeader(id), std::move(p), t};
}

TEST_CASE("database loads and knows fast vs single") {
    REQUIRE(db().find(128267)->id == "waterDepth");
    REQUIRE_FALSE(db().isFastPacket(128267));
    REQUIRE(db().isFastPacket(129038));
    REQUIRE(db().isFastPacket(129029));
}
TEST_CASE("missing database file reports an error") {
    REQUIRE_FALSE(n2k::PgnDatabase::load("/nonexistent/canboat.json"));
}
TEST_CASE("decodes water depth with offset") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x0DF50B10, {0xFF,0xA2,0x05,0x00,0x00,0xD4,0xFE,0xFF}));
    REQUIRE(d);
    REQUIRE(d->pgnId == "waterDepth");
    REQUIRE(std::get<double>(d->fields.at("depth")) == Catch::Approx(14.42));
    REQUIRE(std::get<double>(d->fields.at("offset")) == Catch::Approx(-0.3));
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("sid")));
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("range")));
}
TEST_CASE("decodes position rapid update") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x09F80123, {0x30,0x21,0x60,0x1C,0x58,0x9A,0x15,0xB7}));
    REQUIRE(d);
    REQUIRE(std::get<double>(d->fields.at("latitude")) == Catch::Approx(47.6062).epsilon(1e-9));
    REQUIRE(std::get<double>(d->fields.at("longitude")) == Catch::Approx(-122.3321).epsilon(1e-9));
}
TEST_CASE("decodes COG/SOG with lookup name") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x09F80223, {0x01,0xFC,0xE6,0x91,0x49,0x01,0xFF,0xFF}));
    REQUIRE(d);
    REQUIRE(std::get<double>(d->fields.at("cog")) == Catch::Approx(3.7350));
    REQUIRE(std::get<double>(d->fields.at("sog")) == Catch::Approx(3.29));
    REQUIRE(std::get<int64_t>(d->fields.at("cogReference")) == 0);
    REQUIRE(std::get<std::string>(d->fields.at("cogReferenceName")) == "True");
}
TEST_CASE("decodes heading") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x09F11223, {0x00,0x83,0x8F,0xFF,0x7F,0xFF,0x7F,0xFD}));
    REQUIRE(d);
    REQUIRE(std::get<double>(d->fields.at("heading")) == Catch::Approx(3.6739));
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("deviation")));
    REQUIRE(std::get<std::string>(d->fields.at("referenceName")) == "Magnetic");
}
TEST_CASE("decodes water temperature") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x15FD0610, {0x00,0x5D,0x70,0xFF,0xFF,0xFF,0xFF,0xFF}));
    REQUIRE(d);
    REQUIRE(std::get<double>(d->fields.at("waterTemperature")) == Catch::Approx(287.65));
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("atmosphericPressure")));
}
TEST_CASE("all-ones depth is not available, never a huge number") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x0DF50B10, {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x7F,0xFF}));
    REQUIRE(d);
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("depth")));
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("offset")));
}
TEST_CASE("heading raw 0xFFFF exceeds rangeMax and is not available") {
    auto d = n2k::PgnDecoder(db()).decode(msg(0x09F11223, {0x00,0xFF,0xFF,0xFF,0x7F,0xFF,0x7F,0xFD}));
    REQUIRE(d);
    REQUIRE(std::holds_alternative<std::monostate>(d->fields.at("heading")));
}
TEST_CASE("unknown PGN decodes to nullopt") {
    REQUIRE_FALSE(n2k::PgnDecoder(db()).decode(msg(n2k::makeCanId(7, 0x1FFFE, 1), {0,0,0,0,0,0,0,0})));
}
TEST_CASE("decodes AIS class A position report from 28-byte payload") {
    std::vector<uint8_t> p = {0x01, 0xFA,0xDB,0xE1,0x15, 0x00,0x3E,0x0B,0xB7, 0x40,0x71,0x6E,0x1C, 0x00, 0xE6,0x91, 0x49,0x01, 0x00,0x00,0x00, 0x83,0x8F, 0xFF,0x7F, 0xF0, 0xFF, 0xFF};
    auto d = n2k::PgnDecoder(db()).decode(msg(0x11F80E30, p));
    REQUIRE(d);
    REQUIRE(std::get<int64_t>(d->fields.at("userId")) == 367123450);
    REQUIRE(std::get<double>(d->fields.at("longitude")) == Catch::Approx(-122.40).epsilon(1e-9));
    REQUIRE(std::get<double>(d->fields.at("latitude")) == Catch::Approx(47.70).epsilon(1e-9));
    REQUIRE(std::get<double>(d->fields.at("cog")) == Catch::Approx(3.7350));
    REQUIRE(std::get<double>(d->fields.at("heading")) == Catch::Approx(3.6739));
    REQUIRE(std::get<int64_t>(d->fields.at("navStatus")) == 0);
}
