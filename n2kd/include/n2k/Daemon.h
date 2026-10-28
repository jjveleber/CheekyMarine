#pragma once
#include <atomic>
#include <expected>
#include <filesystem>
#include <fstream>
#include <memory>
#include <optional>
#include <string>
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
    bool claimAddress = true;           // --no-claim
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
