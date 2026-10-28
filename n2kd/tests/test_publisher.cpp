#include <catch2/catch_test_macros.hpp>
#include <algorithm>
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
    REQUIRE(lines.size() >= 2);
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
    REQUIRE(readLines(c2, 3).size() >= 3);
    close(c2);
    std::filesystem::remove(path);
}

TEST_CASE("a client that never reads is queued up to the cap, then dropped; others keep receiving") {
    auto path = tmpSock();
    auto pub = *n2k::Publisher::listen(path);
    int stalled = connectUnix(path);
    int reader = connectUnix(path);
    pub.acceptPending();
    REQUIRE(pub.clientCount() == 2);
    // Each line is about 300 KB, larger than a default Unix socket send buffer.
    const nlohmann::json big = {{"type", "ais"}, {"pad", std::string(300 * 1024, 'x')}};
    size_t newlines = 0;
    // Flushes queued bytes and reads the reader's socket until it has `want` lines.
    auto drain = [&](size_t want) {
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        while (newlines < want && std::chrono::steady_clock::now() < deadline) {
            pub.flushPending();
            pollfd p{reader, POLLIN, 0};
            if (::poll(&p, 1, 10) <= 0) continue;
            char tmp[65536];
            ssize_t r = ::read(reader, tmp, sizeof(tmp));
            if (r <= 0) break;
            newlines += static_cast<size_t>(std::count(tmp, tmp + r, '\n'));
        }
    };
    for (size_t i = 0; i < 40; ++i) {
        pub.broadcast(big);
        // 13 lines (3.9 MB) fit in the 4 MB queue even if the socket took nothing.
        if (i < 13) REQUIRE(pub.clientCount() == 2);
        drain(i + 2);  // hello plus i + 1 lines
        REQUIRE(newlines == i + 2);
    }
    // 40 lines (12 MB) exceed the socket buffer plus the queue: the stalled client is gone.
    REQUIRE(pub.clientCount() == 1);
    pub.broadcast({{"type", "vessel"}});
    drain(42);
    REQUIRE(newlines == 42);
    close(stalled);
    close(reader);
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
