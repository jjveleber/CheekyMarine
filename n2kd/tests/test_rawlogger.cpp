#include <unistd.h>

#include <algorithm>
#include <catch2/catch_test_macros.hpp>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "n2k/LogFileSource.h"
#include "n2k/RawLogger.h"

namespace {
std::filesystem::path tmpDir() {
    static int n = 0;
    auto d = std::filesystem::temp_directory_path() /
             ("n2k-rawlog-test-" + std::to_string(::getpid()) + "-" + std::to_string(n++));
    std::filesystem::remove_all(d);
    return d;
}
std::vector<std::filesystem::path> sortedLogFiles(const std::filesystem::path& dir) {
    std::vector<std::filesystem::path> v;
    for (auto& e : std::filesystem::directory_iterator(dir))
        if (e.path().extension() == ".log") v.push_back(e.path());
    std::sort(v.begin(), v.end());
    return v;
}
}  // namespace

TEST_CASE("raw logger writes replayable candump lines and rotates") {
    auto dir = tmpDir();
    {
        n2k::RawLogger log(dir, "can0", 200, 2);
        for (int i = 0; i < 20; ++i)
            log.write({0x09F80123, 8, {0x30, 0x21, 0x60, 0x1C, 0x58, 0x9A, 0x15, 0xB7}, 1700000000.0 + i});
        log.flush();
    }
    auto files = sortedLogFiles(dir);
    REQUIRE(files.size() == 2);
    std::ifstream in(files.back());
    n2k::LogFileSource src(in);
    auto f = src.next();
    REQUIRE(f);
    REQUIRE(f->id == 0x09F80123);
    REQUIRE(f->data[7] == 0xB7);
    std::filesystem::remove_all(dir);
}
