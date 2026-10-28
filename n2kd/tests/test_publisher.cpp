#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>

#include "SocketTestHelpers.h"
#include "n2k/Publisher.h"

TEST_CASE("client receives hello then broadcasts, newline delimited") {
    auto path = tmpSock();
    auto pub = *n2k::Publisher::listen(path);
    int c = connectUnix(path);
    pub.acceptPending();
    REQUIRE(pub.clientCount() == 1);
    pub.broadcast({{"type", "vessel"}, {"t", 1.0}});
    auto lines = readLines(c, 2);
    REQUIRE(lines.size() == 2);
    REQUIRE(nlohmann::json::parse(lines[0])["type"] == "hello");
    REQUIRE(nlohmann::json::parse(lines[1])["type"] == "vessel");
    close(c);
    std::filesystem::remove(path);
}

TEST_CASE("disconnected client is dropped without killing the process") {
    auto path = tmpSock();
    auto pub = *n2k::Publisher::listen(path);
    int c1 = connectUnix(path);
    int c2 = connectUnix(path);
    pub.acceptPending();
    REQUIRE(pub.clientCount() == 2);
    close(c1);
    pub.broadcast({{"type", "vessel"}});
    pub.broadcast({{"type", "vessel"}});
    REQUIRE(pub.clientCount() == 1);
    REQUIRE(readLines(c2, 3).size() == 3);
    close(c2);
    std::filesystem::remove(path);
}

TEST_CASE("stale socket file is replaced on listen") {
    auto path = tmpSock();
    bindAndAbandon(path);
    REQUIRE(n2k::Publisher::listen(path));
    std::filesystem::remove(path);
}

TEST_CASE("listen rejects an over-long path") {
    auto r = n2k::Publisher::listen(std::filesystem::path("/tmp/" + std::string(200, 'x')));
    REQUIRE_FALSE(r);
}
