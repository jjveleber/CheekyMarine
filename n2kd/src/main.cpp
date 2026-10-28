#include <signal.h>

#include <atomic>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>

#include "n2k/Daemon.h"
#include "n2k/PgnDatabase.h"
#include "n2k/Version.h"

namespace {

std::atomic<bool> gStop{false};

void onSignal(int) { gStop = true; }

constexpr const char* kUsage =
    "usage: n2kd (--can IFACE | --replay FILE) [options]\n"
    "  --can IFACE     read live frames from a SocketCAN interface (e.g. can0)\n"
    "  --replay FILE   replay a candump -L or canboat RAW log\n"
    "  --speed N       replay speed factor, 0 = as fast as possible (default 1)\n"
    "  --socket PATH   Unix socket to serve JSON on (default /run/cheekymarine/n2k.sock)\n"
    "  --stdout        print JSON snapshots to stdout instead of serving a socket\n"
    "  --rawlog DIR    write raw frames to rotating candump -L files in DIR\n"
    "  --pgns PATH     canboat.json PGN database (default: installed copy, else source tree)\n"
    "  --hz N          publish rate in Hz (default 2)\n"
    "  --no-claim      do not send an ISO address claim on the CAN bus\n"
    "  --help          show this help\n"
    "  --version       show the version\n";

std::optional<double> parseNumber(std::string_view s) {
    std::string tmp(s);
    char* end = nullptr;
    double v = std::strtod(tmp.c_str(), &end);
    if (tmp.empty() || end != tmp.c_str() + tmp.size() || !std::isfinite(v)) return std::nullopt;
    return v;
}

int badOption(const std::string& msg) {
    std::cerr << "n2kd: " << msg << "\n" << kUsage;
    return 1;
}

std::filesystem::path defaultCanboatJson() {
    std::error_code ec;
    if (std::filesystem::exists(N2K_CANBOAT_JSON_INSTALLED, ec)) return N2K_CANBOAT_JSON_INSTALLED;
    return N2K_CANBOAT_JSON;
}

}  // namespace

int main(int argc, char** argv) {
    n2k::DaemonOptions opts;
    bool pgnsGiven = false;
    for (int i = 1; i < argc; ++i) {
        std::string_view a = argv[i];
        auto value = [&]() -> std::optional<std::string> {
            if (i + 1 >= argc) return std::nullopt;
            return std::string(argv[++i]);
        };
        if (a == "--help") {
            std::cout << kUsage;
            return 0;
        } else if (a == "--version") {
            std::cout << "n2kd " << n2k::version() << "\n";
            return 0;
        } else if (a == "--stdout") {
            opts.stdoutJson = true;
        } else if (a == "--no-claim") {
            opts.claimAddress = false;
        } else if (a == "--can" || a == "--replay" || a == "--speed" || a == "--socket" || a == "--rawlog" ||
                   a == "--pgns" || a == "--hz") {
            auto v = value();
            if (!v) return badOption("missing value for " + std::string(a));
            if (a == "--can") {
                opts.canInterface = *v;
            } else if (a == "--replay") {
                opts.replayFile = *v;
            } else if (a == "--socket") {
                opts.socketPath = *v;
            } else if (a == "--rawlog") {
                opts.rawLogDir = *v;
            } else if (a == "--pgns") {
                opts.canboatJson = *v;
                pgnsGiven = true;
            } else {
                auto n = parseNumber(*v);
                if (a == "--speed") {
                    if (!n || *n < 0) return badOption("--speed needs a number >= 0");
                    opts.replaySpeed = *n;
                } else {
                    if (!n || *n <= 0) return badOption("--hz needs a number > 0");
                    opts.publishHz = *n;
                }
            }
        } else {
            return badOption("unknown option " + std::string(a));
        }
    }
    if (opts.canInterface.has_value() == opts.replayFile.has_value()) {
        return badOption("exactly one of --can or --replay is required");
    }
    if (!pgnsGiven) opts.canboatJson = defaultCanboatJson();

    auto db = n2k::PgnDatabase::load(opts.canboatJson);
    if (!db) {
        std::cerr << "n2kd: " << db.error() << "\n";
        return 2;
    }

    ::signal(SIGPIPE, SIG_IGN);
    struct sigaction sa{};
    sa.sa_handler = onSignal;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGINT, &sa, nullptr);

    auto daemon = n2k::Daemon::create(std::move(opts), std::move(*db));
    if (!daemon) {
        std::cerr << "n2kd: " << daemon.error() << "\n";
        return 1;
    }
    return daemon->run(gStop);
}
