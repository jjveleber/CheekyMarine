#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include <catch2/catch_test_macros.hpp>
#include <chrono>
#include <filesystem>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "SocketTestHelpers.h"

namespace {

std::string FIXTURE(const std::string& name) { return std::string(N2K_FIXTURE_DIR) + "/" + name; }

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
    auto proc = startDaemon({"--replay", FIXTURE("garmin-airmar.log"), "--speed", "50", "--socket", path.string(),
                             "--no-claim"});
    int c = connectUnixRetry(path, 2.0);
    REQUIRE(c >= 0);
    auto lines = readLines(c, 3, 5.0);
    REQUIRE(lines.size() == 3);
    REQUIRE(nlohmann::json::parse(lines[0])["type"] == "hello");
    ::close(c);
    proc.terminate();
    REQUIRE(proc.wait() == 0);
}

TEST_CASE("bad options exit 1, missing pgns file exits 2") {
    REQUIRE(runDaemon({"--bogus"}).exitCode == 1);
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--pgns", "/nonexistent.json", "--stdout"}).exitCode == 2);
}

TEST_CASE("garbage lines in replay do not stop the daemon") {
    REQUIRE(runDaemon({"--replay", FIXTURE("mixed.log"), "--speed", "0", "--stdout", "--no-claim"}).exitCode == 0);
}
