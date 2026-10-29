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

namespace {
void touch(const std::filesystem::path& p) { std::ofstream(p) << "(1.000000) can0 09F80123#0000000000000000\n"; }
n2k::CanFrame sampleFrame(double t) { return {0x09F80123, 8, {0x30, 0x21, 0x60, 0x1C, 0x58, 0x9A, 0x15, 0xB7}, t}; }
}  // namespace

TEST_CASE("raw logger never prunes the file it is writing, even when old files sort after now") {
    auto dir = tmpDir();
    std::filesystem::create_directories(dir);
    for (int s = 1; s <= 5; ++s)
        touch(dir / ("n2k-00000" + std::to_string(s) + "-20991231-23595" + std::to_string(s) + ".log"));
    {
        n2k::RawLogger log(dir, "can0", 1 << 20, 2);
        log.write(sampleFrame(1700000000.0));
        log.flush();
        auto files = sortedLogFiles(dir);
        REQUIRE(files.size() == 2);
        REQUIRE(files.front().filename().string() == "n2k-000005-20991231-235955.log");
        REQUIRE(files.back().filename().string().rfind("n2k-000006-", 0) == 0);
        std::ifstream in(files.back());
        n2k::LogFileSource src(in);
        auto f = src.next();
        REQUIRE(f);
        REQUIRE(f->timestamp == 1700000000.0);
    }
    std::filesystem::remove_all(dir);
}

TEST_CASE("raw logger continues the sequence of files left by a previous run") {
    auto dir = tmpDir();
    {
        n2k::RawLogger log(dir, "can0", 200, 10);
        for (int i = 0; i < 6; ++i) log.write(sampleFrame(1700000000.0 + i));
    }
    auto before = sortedLogFiles(dir);
    REQUIRE(before.size() == 2);
    REQUIRE(before.back().filename().string().rfind("n2k-000002-", 0) == 0);
    {
        n2k::RawLogger log(dir, "can0", 200, 10);
        log.write(sampleFrame(1800000000.0));
    }
    auto after = sortedLogFiles(dir);
    REQUIRE(after.size() == 3);
    REQUIRE(after.back().filename().string().rfind("n2k-000003-", 0) == 0);
    std::ifstream in(after.back());
    n2k::LogFileSource src(in);
    auto f = src.next();
    REQUIRE(f);
    REQUIRE(f->timestamp == 1800000000.0);
    REQUIRE_FALSE(src.next());
    std::filesystem::remove_all(dir);
}
