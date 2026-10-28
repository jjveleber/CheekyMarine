#pragma once
#include <algorithm>
#include <atomic>
#include <cstddef>
#include <expected>
#include <filesystem>
#include <fstream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "n2k/PgnDatabase.h"
#include "n2k/Publisher.h"

namespace n2k {

struct DaemonOptions {
    std::optional<std::string> canInterface;                          // --can can0
    std::optional<std::filesystem::path> replayFile;                  // --replay FILE
    double replaySpeed = 1.0;                                         // --speed N (0 = as fast as possible)
    std::filesystem::path socketPath = "/run/cheekymarine/n2k.sock";  // --socket PATH
    std::optional<std::filesystem::path> rawLogDir;                   // --rawlog DIR
    std::filesystem::path canboatJson;  // --pgns PATH; main picks the installed or source-tree default
    double publishHz = 2.0;             // --hz
    bool stdoutJson = false;            // --stdout: print snapshots instead of serving a socket
    bool claimAddress = false;          // --claim (experimental; --no-claim is accepted and keeps it off)
    size_t maxAisTargets = 500;         // --max-ais N: most recently seen targets published per AIS message
};

// Applies a value-less flag (--stdout, --claim, --no-claim) to o; false if a is not one.
bool applyFlagOption(DaemonOptions& o, std::string_view a);

// Publish tick scheduling. due() returns true on the first call, once at least
// `period` seconds have passed since the last tick, or when the clock went
// backwards past the last tick; a true result records now as the last tick.
class TickSchedule {
public:
    explicit TickSchedule(double period) : period_(period) {}
    bool due(double now) {
        if (last_ && now >= *last_ && now - *last_ < period_) return false;
        last_ = now;
        return true;
    }
    double secondsUntilDue(double now) const {
        if (!last_ || now < *last_) return 0.0;
        return std::max(0.0, *last_ + period_ - now);
    }

private:
    double period_;
    std::optional<double> last_;
};

class Daemon {
public:
    // The database is loaded by the caller so that a load failure can map to its own
    // exit code (2); every failure reported here is an exit-1 condition (socket or
    // replay file). Exactly one of canInterface / replayFile must be set.
    static std::expected<Daemon, std::string> create(DaemonOptions opts, PgnDatabase db);

    Daemon(const Daemon&) = delete;
    Daemon& operator=(const Daemon&) = delete;
    Daemon(Daemon&&) = default;
    Daemon& operator=(Daemon&&) = default;

    int run(std::atomic<bool>& stop);  // returns exit code; 0 on clean stop or end of replay file

private:
    Daemon(DaemonOptions opts, PgnDatabase db) : opts_(std::move(opts)), db_(std::make_unique<PgnDatabase>(std::move(db))) {}

    DaemonOptions opts_;
    std::unique_ptr<PgnDatabase> db_;        // heap so decoder references survive a move
    std::optional<Publisher> pub_;           // unset in --stdout mode
    std::unique_ptr<std::ifstream> replay_;  // set in replay mode
};

}  // namespace n2k
