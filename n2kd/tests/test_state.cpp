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
TEST_CASE("Aged value stamped in the future is stale beyond a one-second tolerance") {
    n2k::Aged<double> a;
    a.set(1.5, 100);
    REQUIRE(a.fresh(99.5, 5));          // within SO_TIMESTAMP vs wall-clock skew
    REQUIRE_FALSE(a.fresh(98.9, 5));    // clock stepped back: not current
    a.set(2.0, 1e300);
    REQUIRE_FALSE(a.fresh(5, 5));
}
TEST_CASE("AIS target last seen in the future expires") {
    n2k::AisTargets t;
    t.upsert(367123450, 1000);
    t.upsert(316000001, 100.5);
    REQUIRE(t.expire(100) == 1);        // 367123450 is 900 s in the future
    REQUIRE(t.find(367123450) == nullptr); REQUIRE(t.find(316000001) != nullptr);
}
