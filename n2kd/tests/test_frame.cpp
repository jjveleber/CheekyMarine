#include <catch2/catch_test_macros.hpp>
#include "n2k/Frame.h"

TEST_CASE("PDU2 header: position rapid update") {
    auto h = n2k::parseHeader(0x09F80123);
    REQUIRE(h.priority == 2);
    REQUIRE(h.pgn == 129025);
    REQUIRE(h.source == 0x23);
    REQUIRE(h.destination == 255);
}

TEST_CASE("PDU1 header: address claim carries destination in PS byte") {
    auto h = n2k::parseHeader(0x18EEFFFE);
    REQUIRE(h.priority == 6);
    REQUIRE(h.pgn == 60928);
    REQUIRE(h.source == 0xFE);
    REQUIRE(h.destination == 0xFF);
}

TEST_CASE("PDU1 header: ISO request to a specific address") {
    auto h = n2k::parseHeader(0x18EA2301);
    REQUIRE(h.pgn == 59904);
    REQUIRE(h.destination == 0x23);
    REQUIRE(h.source == 0x01);
}

TEST_CASE("makeCanId round-trips") {
    REQUIRE(n2k::makeCanId(2, 129025, 0x23) == 0x09F80123);
    REQUIRE(n2k::makeCanId(6, 60928, 0xFE, 0xFF) == 0x18EEFFFE);
    REQUIRE(n2k::makeCanId(3, 128267, 0x10) == 0x0DF50B10);
}
