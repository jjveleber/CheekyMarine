#include <catch2/catch_test_macros.hpp>
#include "n2k/Version.h"
TEST_CASE("version matches CMake project version") {
    REQUIRE(n2k::version() == "0.1.0");
}
