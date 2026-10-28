#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>

#include "n2k/AisTargets.h"
#include "n2k/Json.h"
#include "n2k/Version.h"
#include "n2k/VesselState.h"

TEST_CASE("vessel snapshot nulls stale fields and keeps fresh ones") {
    n2k::VesselState vs; vs.position.set({47.6062, -122.3321}, 100); vs.depth.set(14.42, 104); vs.sog.set(3.29, 100);
    auto j = n2k::vesselSnapshot(vs, 105.1);
    REQUIRE(j["type"] == "vessel"); REQUIRE(j["t"] == 105.1);
    REQUIRE(j["pos"].is_null()); REQUIRE(j["sog"].is_null());
    REQUIRE(j["depth"] == Catch::Approx(14.42)); REQUIRE(j["stw"].is_null()); REQUIRE(j.contains("rpm"));
}
TEST_CASE("ais snapshot includes age and sorted targets") {
    n2k::AisTargets a; a.upsert(367123450, 100).lat = 47.7; a.upsert(316000001, 101);
    auto j = n2k::aisSnapshot(a, 102.5);
    REQUIRE(j["targets"].size() == 2); REQUIRE(j["targets"][0]["mmsi"] == 316000001);
    REQUIRE(j["targets"][1]["age"] == Catch::Approx(2.5)); REQUIRE(j["targets"][1]["name"].is_null());
}
TEST_CASE("hello carries schema and version") {
    auto j = n2k::helloMessage(); REQUIRE(j["schema"] == 1);
    REQUIRE(j["version"].get<std::string>() == std::string(n2k::version()));
}
