#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <catch2/catch_test_macros.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "SocketTestHelpers.h"
#include "n2k/Daemon.h"

namespace {

std::string FIXTURE(const std::string& name) { return std::string(N2K_FIXTURE_DIR) + "/" + name; }

// Writes content to a fresh temporary log file and returns its path.
std::string writeTempLog(const std::string& content) {
    static int counter = 0;
    auto p = std::filesystem::temp_directory_path() /
             ("n2kd-test-" + std::to_string(::getpid()) + "-" + std::to_string(counter++) + ".log");
    std::ofstream(p) << content;
    return p.string();
}

// The 4-frame class B position report for MMSI 338123456 from ais-static.log, stamped t.
std::string aisReportAt(double t) {
    std::string out;
    for (const char* data : {"201B12C05A271400", "213E0BB740716E1C", "22FF3930FA00FFFF", "23FFFFFFFFFFFFFF"}) {
        out += "(" + std::to_string(t) + ") can0 1DF80F31#" + data + "\n";
    }
    return out;
}

// All JSON lines of the given type in out.
std::vector<nlohmann::json> jsonLinesOfType(const std::string& out, const std::string& type) {
    std::vector<nlohmann::json> lines;
    std::istringstream in(out);
    std::string line;
    while (std::getline(in, line)) {
        auto j = nlohmann::json::parse(line, nullptr, false);
        if (j.is_object() && j.value("type", "") == type) lines.push_back(j);
    }
    return lines;
}

// Forks and execs the built daemon; stdout goes to stdoutFd if >= 0, else is inherited.
pid_t spawnDaemon(const std::vector<std::string>& args, int stdoutFd) {
    std::vector<char*> argv;
    std::string bin = N2KD_BINARY;
    argv.push_back(bin.data());
    std::vector<std::string> copy = args;
    for (auto& a : copy) argv.push_back(a.data());
    argv.push_back(nullptr);
    pid_t pid = ::fork();
    if (pid == 0) {
        if (stdoutFd >= 0) ::dup2(stdoutFd, STDOUT_FILENO);
        ::execv(bin.c_str(), argv.data());
        ::_exit(127);
    }
    return pid;
}

int exitCodeOf(int status) { return WIFEXITED(status) ? WEXITSTATUS(status) : -1; }

// Waits up to timeoutSeconds; kills and returns -1 on timeout.
int waitWithTimeout(pid_t pid, double timeoutSeconds) {
    auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeoutSeconds);
    int status = 0;
    while (::waitpid(pid, &status, WNOHANG) == 0) {
        if (std::chrono::steady_clock::now() > deadline) {
            ::kill(pid, SIGKILL);
            ::waitpid(pid, &status, 0);
            return -1;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return exitCodeOf(status);
}

struct RunResult {
    int exitCode;
    std::string stdout;
};

// Runs the daemon to completion (10 s timeout, killed on timeout), capturing stdout.
RunResult runDaemon(const std::vector<std::string>& args) {
    int p[2];
    REQUIRE(::pipe2(p, O_CLOEXEC) == 0);
    pid_t pid = spawnDaemon(args, p[1]);
    ::close(p[1]);
    RunResult r{-1, {}};
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    for (;;) {
        auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now());
        if (left.count() <= 0) break;
        pollfd pf{p[0], POLLIN, 0};
        if (::poll(&pf, 1, static_cast<int>(left.count())) <= 0) break;
        char buf[65536];
        ssize_t n = ::read(p[0], buf, sizeof(buf));
        if (n <= 0) break;
        r.stdout.append(buf, static_cast<size_t>(n));
    }
    ::close(p[0]);
    auto left = std::chrono::duration<double>(deadline - std::chrono::steady_clock::now()).count();
    r.exitCode = waitWithTimeout(pid, left > 0 ? left : 0);
    return r;
}

struct DaemonProcess {
    pid_t pid;
    void terminate() const { ::kill(pid, SIGTERM); }
    int wait() {
        int code = waitWithTimeout(pid, 10.0);
        pid = -1;
        return code;
    }
    ~DaemonProcess() {
        if (pid > 0) {
            ::kill(pid, SIGKILL);
            ::waitpid(pid, nullptr, 0);
        }
    }
};

DaemonProcess startDaemon(const std::vector<std::string>& args) { return {spawnDaemon(args, -1)}; }

int connectUnixRetry(const std::filesystem::path& path, double timeoutSeconds) {
    auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeoutSeconds);
    for (;;) {
        int fd = connectUnix(path);
        if (fd >= 0 || std::chrono::steady_clock::now() > deadline) return fd;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
}

// Last line of stdout that parses as JSON with the given "type"; null if none.
nlohmann::json lastJsonLineOfType(const std::string& out, const std::string& type) {
    nlohmann::json last;
    std::istringstream in(out);
    std::string line;
    while (std::getline(in, line)) {
        auto j = nlohmann::json::parse(line, nullptr, false);
        if (j.is_object() && j.value("type", "") == type) last = j;
    }
    return last;
}

}  // namespace

TEST_CASE("replay of Garmin/Airmar log yields a populated vessel snapshot on stdout") {
    auto out = runDaemon({"--replay", FIXTURE("garmin-airmar.log"), "--speed", "0", "--stdout", "--no-claim"});
    REQUIRE(out.exitCode == 0);
    auto last = lastJsonLineOfType(out.stdout, "vessel");
    REQUIRE(last["pos"]["lat"].is_number());
    // Every 128267 frame in this sample reports depth as "not available" (0xFFFFFFFF); the
    // offset field of the same PGN is valid, so it proves the depth PGN flowed end to end.
    REQUIRE(last["depthOffset"].is_number());
    REQUIRE(last["sog"].is_number());
    REQUIRE(last["waterTemp"].is_number());
}

TEST_CASE("replay serves clients over the socket") {
    auto path = tmpSock();
    // Speed 1: the 12 s replay must outlast the client connect and three lines.
    auto proc = startDaemon({"--replay", FIXTURE("garmin-airmar.log"), "--speed", "1", "--socket", path.string(),
                             "--no-claim"});
    int c = connectUnixRetry(path, 5.0);
    REQUIRE(c >= 0);
    auto lines = readLines(c, 3, 5.0);
    REQUIRE(lines.size() >= 3);
    REQUIRE(nlohmann::json::parse(lines[0])["type"] == "hello");
    ::close(c);
    proc.terminate();
    REQUIRE(proc.wait() == 0);
}

TEST_CASE("bad options exit 1, missing pgns file exits 2") {
    REQUIRE(runDaemon({"--bogus"}).exitCode == 1);
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--stdout", "--max-ais", "0"}).exitCode == 1);
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--stdout", "--max-ais", "2.5"}).exitCode == 1);
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--pgns", "/nonexistent.json", "--stdout"}).exitCode == 2);
}

TEST_CASE("garbage lines in replay do not stop the daemon") {
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--speed", "0", "--stdout", "--no-claim"}).exitCode == 0);
}

TEST_CASE("tick schedule fires on period and after a backward clock step") {
    n2k::TickSchedule s(0.5);
    REQUIRE(s.due(1000.0));        // first call
    REQUIRE_FALSE(s.due(1000.2));  // within period
    REQUIRE(s.due(1000.5));        // period elapsed
    REQUIRE(s.due(400.0));         // clock stepped back: due at once, not 600 s later
    REQUIRE_FALSE(s.due(400.1));
    REQUIRE(s.due(400.6));
}

TEST_CASE("replay pacing caps each gap at kMaxReplaySleepSeconds of wall time") {
    n2k::ReplayPacer p(1.0);
    REQUIRE(p.due(100.0) == 0.0);
    REQUIRE(p.due(101.5) == 1.5);
    REQUIRE_FALSE(p.capped());
    REQUIRE(p.due(101.5 + 86400) == 1.5 + n2k::kMaxReplaySleepSeconds);  // day gap: capped
    REQUIRE(p.capped());
    REQUIRE(p.due(102.5 + 86400) == 2.5 + n2k::kMaxReplaySleepSeconds);  // later frames keep their pace
    REQUIRE(p.due(50.0) == 2.5 + n2k::kMaxReplaySleepSeconds);           // backward step: no wait
    n2k::ReplayPacer fast(10.0);
    fast.due(0.0);
    REQUIRE(fast.due(20.0) == 2.0);  // 20 s of log at speed 10
    n2k::ReplayPacer slow(0.001);
    slow.due(0.0);
    REQUIRE(slow.due(3.9e9) == n2k::kMaxReplaySleepSeconds);  // huge gap at slow speed stays bounded
}

TEST_CASE("speed below 0.001 is rejected") {
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--speed", "0.0005", "--stdout"}).exitCode == 1);
}

TEST_CASE("late socket client receives current AIS targets even when unchanged") {
    auto path = tmpSock();
    auto proc = startDaemon({"--replay", FIXTURE("ais-static.log"), "--speed", "2", "--socket", path.string(),
                             "--no-claim"});
    auto isTarget = [](const std::string& line) {
        auto j = nlohmann::json::parse(line);
        return j["type"] == "ais" && j["targets"].size() == 1 && j["targets"][0]["mmsi"] == 338123456;
    };
    // Client A waits until the target has been sent once, so its content is unchanged from here on.
    int a = connectUnixRetry(path, 5.0);
    REQUIRE(a >= 0);
    bool aGotAis = false;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!aGotAis && std::chrono::steady_clock::now() < deadline) {
        for (const auto& line : readLines(a, 1, 0.5)) aGotAis = aGotAis || isTarget(line);
    }
    REQUIRE(aGotAis);
    // Client B connects after that send (before the static reports end at 3.5 s) and must get it.
    int b = connectUnixRetry(path, 5.0);
    REQUIRE(b >= 0);
    auto lines = readLines(b, 3, 5.0);
    REQUIRE(lines.size() >= 3);
    lines.resize(3);
    REQUIRE(std::any_of(lines.begin(), lines.end(), isTarget));
    ::close(a);
    ::close(b);
    proc.terminate();
    REQUIRE(proc.wait() == 0);
}

TEST_CASE("an empty ais message is sent when the last target expires") {
    auto out = runDaemon({"--replay", FIXTURE("ais-static.log"), "--speed", "0", "--stdout", "--no-claim"});
    REQUIRE(out.exitCode == 0);
    std::vector<nlohmann::json> ais;
    std::istringstream in(out.stdout);
    std::string line;
    while (std::getline(in, line)) {
        auto j = nlohmann::json::parse(line);
        if (j["type"] == "ais") ais.push_back(j);
    }
    REQUIRE(ais.size() == 2);  // first sighting, then the expiry at t = 1000
    REQUIRE(ais[0]["targets"].size() == 1);
    REQUIRE(ais[1]["targets"].empty());
}

TEST_CASE("address claiming is off by default and enabled only by --claim") {
    n2k::DaemonOptions o;
    REQUIRE_FALSE(o.claimAddress);
    REQUIRE(n2k::applyFlagOption(o, "--claim"));
    REQUIRE(o.claimAddress);
    REQUIRE(n2k::applyFlagOption(o, "--no-claim"));
    REQUIRE_FALSE(o.claimAddress);
    REQUIRE(n2k::applyFlagOption(o, "--stdout"));
    REQUIRE(o.stdoutJson);
    REQUIRE_FALSE(n2k::applyFlagOption(o, "--can"));
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--speed", "0", "--stdout", "--claim"}).exitCode == 0);
}

TEST_CASE("an unchanged AIS target is re-sent at least every kAisRefreshSeconds") {
    // One report at t = 1, then 30 s of unrelated single frames (ISO requests) once a second.
    std::string log = aisReportAt(1.0);
    for (int t = 2; t <= 31; ++t) log += "(" + std::to_string(t) + ".000000) can0 18EAFF01#14F001\n";
    auto path = writeTempLog(log);
    auto out = runDaemon({"--replay", path, "--speed", "0", "--stdout", "--no-claim", "--pgns", N2K_CANBOAT_JSON});
    std::filesystem::remove(path);
    REQUIRE(out.exitCode == 0);
    auto ais = jsonLinesOfType(out.stdout, "ais");
    REQUIRE(ais.size() >= 3);
    REQUIRE(ais.back()["targets"].size() == 1);
    REQUIRE(ais.back()["targets"][0]["age"].get<double>() > n2k::kAisRefreshSeconds);
}
