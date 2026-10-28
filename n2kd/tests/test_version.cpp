#include <catch2/catch_test_macros.hpp>
#include <regex>
#include <string>

#include "n2k/Version.h"

TEST_CASE("version matches CMake project version") {
    REQUIRE(n2k::version() == N2K_EXPECTED_VERSION);
    REQUIRE(std::regex_match(std::string(N2K_EXPECTED_VERSION), std::regex(R"(^[0-9]+\.[0-9]+\.[0-9]+$)")));
}
