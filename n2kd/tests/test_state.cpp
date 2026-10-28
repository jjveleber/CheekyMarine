#include <catch2/catch_test_macros.hpp>
#include "n2k/VesselState.h"
#include "n2k/AisTargets.h"

TEST_CASE("Aged value freshness") {
    n2k::Aged<double> a; REQUIRE_FALSE(a.fresh(10, 5));
    a.set(1.5, 10); REQUIRE(a.fresh(14.9, 5)); REQUIRE_FALSE(a.fresh(15.1, 5));
}
TEST_CASE("AIS upsert keeps static data and expires by age") {
    n2k::AisTargets t;
    t.upsert(367123450, 100).name = "ARGOSY";
    t.upsert(367123450, 200).sog = 3.0;
    REQUIRE(t.find(367123450)->name == "ARGOSY"); REQUIRE(t.find(367123450)->lastSeen == 200);
    t.upsert(316000001, 150);
    REQUIRE(t.expire(760) == 1);            // 316000001 last seen 150, age 610 > 600
    REQUIRE(t.find(316000001) == nullptr); REQUIRE(t.find(367123450) != nullptr);
}
