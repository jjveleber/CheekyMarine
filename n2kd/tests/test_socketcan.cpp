#include <unistd.h>

#include <catch2/catch_test_macros.hpp>
#include <string>

#include "n2k/SocketCanSource.h"

TEST_CASE("open fails cleanly on a missing interface") {
    auto r = n2k::SocketCanSource::open("nosuchcan9");
    REQUIRE_FALSE(r);
    REQUIRE(r.error().find("nosuchcan9") != std::string::npos);
}

TEST_CASE("vcan round trip", "[vcan]") {
    auto a = n2k::SocketCanSource::open("vcan0");
    auto b = n2k::SocketCanSource::open("vcan0");
    if (!a || !b) SKIP("vcan0 not present");
    n2k::CanFrame f{0x09F80123, 8, {0x30, 0x21, 0x60, 0x1C, 0x58, 0x9A, 0x15, 0xB7}, 0};
    REQUIRE(a->send(f));
    std::optional<n2k::CanFrame> got;
    for (int i = 0; i < 100 && !got; ++i) {
        got = b->next();
        if (!got) usleep(1000);
    }
    REQUIRE(got);
    REQUIRE(got->id == 0x09F80123);
    REQUIRE(got->data[7] == 0xB7);
    REQUIRE(got->timestamp > 1.6e9);
}
