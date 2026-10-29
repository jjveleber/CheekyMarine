#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <sstream>

#include "n2k/Frame.h"
#include "n2k/LogFileSource.h"

TEST_CASE("parses candump -L line") {
    auto f = n2k::LogFileSource::parseLine("(1745600961.335462) can0 09F80123#3021601C589A15B7");
    REQUIRE(f); REQUIRE(f->id == 0x09F80123); REQUIRE(f->len == 8);
    REQUIRE(f->data[0] == 0x30); REQUIRE(f->data[7] == 0xB7);
    REQUIRE(f->timestamp == Catch::Approx(1745600961.335462));
}
TEST_CASE("parses canboat RAW line with legacy timestamp") {
    auto f = n2k::LogFileSource::parseLine("2011-04-25-10:16:42.554,3,128267,4,255,8,25,1b,01,00,00,00,00,ff");
    REQUIRE(f); REQUIRE(f->id == n2k::makeCanId(3, 128267, 4)); REQUIRE(f->len == 8);
    REQUIRE(f->data[1] == 0x1b); REQUIRE(f->timestamp == Catch::Approx(1303726602.554));
}
TEST_CASE("parses canboat RAW line with ISO timestamp") {
    auto f = n2k::LogFileSource::parseLine("2020-08-22T13:52:52.882Z,7,130817,40,255,8,00,71,8c,80,93,02,54,65");
    REQUIRE(f); REQUIRE(f->timestamp == Catch::Approx(1598104372.882));
}
TEST_CASE("rejects garbage and over-long frames") {
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(1.0) can0 09F80123#3021601C589A15B7FF")); // 9 bytes
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(1.0) can0 09F80123#30ZZ"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("hello"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("2011-04-25-10:16:42.554,3,128267,4,255,8,25,1b")); // len says 8, has 2
}
TEST_CASE("stream source yields frames and counts skipped lines") {
    std::istringstream in("# comment\n\n(1.0) can0 09F80123#3021601C589A15B7\nbad line\n(2.0) can0 0DF50B10#FFA2050000D4FEFF\n");
    n2k::LogFileSource src(in);
    REQUIRE(src.next()); REQUIRE(src.next()); REQUIRE_FALSE(src.next());
    REQUIRE(src.skippedLines() == 1);
}

TEST_CASE("rejects non-finite timestamps") {
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(nan) can0 09F80123#3021601C589A15B7"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(inf) can0 09F80123#3021601C589A15B7"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(-inf) can0 09F80123#3021601C589A15B7"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(1e999) can0 09F80123#3021601C589A15B7"));
    std::istringstream in("(nan) can0 09F80123#3021601C589A15B7\n(2.0) can0 0DF50B10#FFA2050000D4FEFF\n");
    n2k::LogFileSource src(in);
    REQUIRE(src.next()); REQUIRE_FALSE(src.next());
    REQUIRE(src.skippedLines() == 1);
}

TEST_CASE("rejects timestamps after year 2096 (above 4e9) as unparseable") {
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(1e300) can0 09F80123#3021601C589A15B7"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("(4000000000.5) can0 09F80123#3021601C589A15B7"));
    REQUIRE_FALSE(n2k::LogFileSource::parseLine("2100-01-01-00:00:00.000,3,128267,4,255,8,25,1b,01,00,00,00,00,ff"));
    REQUIRE(n2k::LogFileSource::parseLine("(3999999999.0) can0 09F80123#3021601C589A15B7"));
    std::istringstream in("(1e300) can0 09F80123#3021601C589A15B7\n(2.0) can0 0DF50B10#FFA2050000D4FEFF\n");
    n2k::LogFileSource src(in);
    REQUIRE(src.next()); REQUIRE_FALSE(src.next());
    REQUIRE(src.skippedLines() == 1);
}
