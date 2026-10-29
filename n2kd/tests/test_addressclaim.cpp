#include <catch2/catch_test_macros.hpp>
#include <string>
#include <variant>

#include "TestHelpers.h"
#include "n2k/AddressClaim.h"

TEST_CASE("address claim frame matches canboat field layout") {
    auto f = n2k::buildAddressClaim({.uniqueNumber = 0x12345});
    REQUIRE(f.id == 0x18EEFFFE);
    REQUIRE(f.len == 8);
    auto d = n2k::PgnDecoder(db()).decode(msg(f.id, {f.data.begin(), f.data.end()}, 0));
    REQUIRE(d);
    REQUIRE(std::get<int64_t>(d->fields.at("uniqueNumber")) == 0x12345);
    REQUIRE(std::get<int64_t>(d->fields.at("deviceFunction")) == 130);
    REQUIRE(std::get<int64_t>(d->fields.at("deviceClass")) == 120);
    REQUIRE(std::get<std::string>(d->fields.at("industryGroupName")) == "Marine Industry");
    REQUIRE(std::get<int64_t>(d->fields.at("arbitraryAddressCapable")) == 1);
}
