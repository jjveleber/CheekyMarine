#include "n2k/Daemon.h"

#include <poll.h>

#include <algorithm>
#include <chrono>
#include <ctime>
#include <iostream>
#include <system_error>
#include <utility>
#include <vector>

#include "n2k/AddressClaim.h"
#include "n2k/AisTargets.h"
#include "n2k/FastPacket.h"
#include "n2k/Json.h"
#include "n2k/LogFileSource.h"
#include "n2k/PgnDecoder.h"
#include "n2k/RawLogger.h"
#include "n2k/SocketCanSource.h"
#include "n2k/StateMappers.h"
#include "n2k/VesselState.h"

namespace n2k {

namespace {

using Steady = std::chrono::steady_clock;

constexpr double kCanRetrySeconds = 5.0;
constexpr int kMaxPollMs = 100;  // bounds latency of noticing stop
// Fixed ISO unique number (21 bits). One n2kd per bus is the expected deployment.
constexpr uint32_t kUniqueNumber = 0x0C4EE;

double wallNow() {
    timespec ts{};
    ::clock_gettime(CLOCK_REALTIME, &ts);
    return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
}

int msUntil(Steady::time_point t) {
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t - Steady::now()).count();
    return static_cast<int>(std::clamp<long long>(ms, 0, kMaxPollMs));
}

// AIS snapshot with the clock-dependent keys removed, for change detection.
nlohmann::json aisContent(nlohmann::json j) {
    j.erase("t");
    for (auto& t : j["targets"]) t.erase("age");
    return j;
}

// All per-run processing state: frame pipeline, models and publishing.
class Pipeline {
public:
    Pipeline(const DaemonOptions& o, const PgnDatabase& db, Publisher* pub)
        : pub_(pub),
          assembler_([&db](uint32_t pgn) { return db.isFastPacket(pgn); }),
          decoder_(db),
          period_(1.0 / o.publishHz) {
        if (o.rawLogDir) rawlog_.emplace(*o.rawLogDir, o.canInterface.value_or("can0"));
    }

    // Order: raw log, fast-packet assembly, decode, map.
    void process(const CanFrame& f) {
        ++frames_;
        if (rawlog_) rawlog_->write(f);
        auto m = assembler_.push(f);
        if (!m) return;
        auto d = decoder_.decode(*m);
        if (!d) {
            ++undecodable_;
            return;
        }
        mappers_.apply(*d, vs_, ais_);
    }

    bool tickDue(double now) const { return !lastTick_ || now - *lastTick_ >= period_; }
    double secondsToTick(double now) const { return lastTick_ ? *lastTick_ + period_ - now : 0.0; }

    void tick(double now) {
        lastTick_ = now;
        assembler_.expire(now);
        ais_.expire(now);
        if (rawlog_) rawlog_->flush();
        if (pub_) pub_->acceptPending();
        emit(vesselSnapshot(vs_, now));
        if (!ais_.all().empty()) {
            auto j = aisSnapshot(ais_, now);
            auto content = aisContent(j);
            if (content != lastAis_) {
                emit(j);
                lastAis_ = std::move(content);
            }
        }
    }

    void summary(size_t skippedLines) const {
        std::cerr << "n2kd: " << frames_ << " frames, " << undecodable_ << " undecodable, "
                  << assembler_.droppedIncomplete() << " incomplete fast packets, " << skippedLines
                  << " skipped lines\n";
    }

private:
    void emit(const nlohmann::json& j) {
        if (pub_) {
            pub_->broadcast(j);
        } else {
            std::cout << j.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) << '\n' << std::flush;
        }
    }

    Publisher* pub_;
    FastPacketAssembler assembler_;
    PgnDecoder decoder_;
    StateMappers mappers_;
    VesselState vs_;
    AisTargets ais_;
    std::optional<RawLogger> rawlog_;
    double period_;
    std::optional<double> lastTick_;
    nlohmann::json lastAis_;
    size_t frames_ = 0;
    size_t undecodable_ = 0;
};

// Polls the listening socket (if any) until deadline or stop, accepting clients.
void waitUntil(Steady::time_point deadline, Publisher* pub, const std::atomic<bool>& stop) {
    while (!stop && Steady::now() < deadline) {
        pollfd p{pub ? pub->fd() : -1, POLLIN, 0};
        ::poll(&p, 1, std::max(1, msUntil(deadline)));
        if (pub && (p.revents & POLLIN)) pub->acceptPending();
    }
}

}  // namespace

std::expected<Daemon, std::string> Daemon::create(DaemonOptions opts, PgnDatabase db) {
    if (opts.canInterface.has_value() == opts.replayFile.has_value()) {
        return std::unexpected("exactly one of --can or --replay is required");
    }

    Daemon d(std::move(opts), std::move(db));
    if (d.opts_.replayFile) {
        d.replay_ = std::make_unique<std::ifstream>(*d.opts_.replayFile);
        if (!*d.replay_) return std::unexpected("cannot open replay file " + d.opts_.replayFile->string());
    }
    if (!d.opts_.stdoutJson) {
        auto parent = d.opts_.socketPath.parent_path();
        std::error_code ec;
        if (!parent.empty()) std::filesystem::create_directories(parent, ec);
        if (ec) return std::unexpected("cannot create " + parent.string() + ": " + ec.message());
        auto pub = Publisher::listen(d.opts_.socketPath);
        if (!pub) return std::unexpected(pub.error());
        d.pub_.emplace(std::move(*pub));
    }
    return d;
}

int Daemon::run(std::atomic<bool>& stop) {
    Publisher* pub = pub_ ? &*pub_ : nullptr;
    Pipeline pipe(opts_, *db_, pub);

    if (replay_) {
        // Replay clock: "now" is the timestamp of the most recent frame.
        LogFileSource src(*replay_);
        std::optional<double> firstTs;
        Steady::time_point wallStart;
        double now = 0;
        bool any = false;
        while (!stop) {
            auto f = src.next();
            if (!f) break;
            if (opts_.replaySpeed > 0) {
                if (!firstTs) {
                    firstTs = f->timestamp;
                    wallStart = Steady::now();
                }
                auto target = wallStart + std::chrono::duration_cast<Steady::duration>(
                                              std::chrono::duration<double>((f->timestamp - *firstTs) / opts_.replaySpeed));
                waitUntil(target, pub, stop);
                if (stop) break;
            }
            pipe.process(*f);
            now = f->timestamp;
            any = true;
            if (pipe.tickDue(now)) pipe.tick(now);
        }
        if (!stop && any) pipe.tick(now);  // final snapshot at end of file
        pipe.summary(src.skippedLines());
        return 0;
    }

    // Live: wall clock; frames carry their SocketCAN timestamps.
    std::optional<SocketCanSource> can;
    auto nextRetry = Steady::now();
    bool loggedOpenError = false;
    auto tryOpen = [&] {
        auto s = SocketCanSource::open(*opts_.canInterface);
        if (!s) {
            if (!loggedOpenError) std::cerr << "n2kd: " << s.error() << " (retrying every 5 s)\n";
            loggedOpenError = true;
            nextRetry = Steady::now() + std::chrono::duration_cast<Steady::duration>(
                                            std::chrono::duration<double>(kCanRetrySeconds));
            return;
        }
        can.emplace(std::move(*s));
        loggedOpenError = false;
        if (opts_.claimAddress) can->send(buildAddressClaim({.uniqueNumber = kUniqueNumber}));
    };

    while (!stop) {
        if (!can && Steady::now() >= nextRetry) tryOpen();
        std::vector<pollfd> fds;
        if (can) fds.push_back({can->fd(), POLLIN, 0});
        if (pub) fds.push_back({pub->fd(), POLLIN, 0});
        int timeout = static_cast<int>(std::clamp(pipe.secondsToTick(wallNow()) * 1000.0 + 1, 0.0, double{kMaxPollMs}));
        ::poll(fds.data(), fds.size(), timeout);
        for (const auto& p : fds) {
            if (can && p.fd == can->fd()) {
                if (p.revents & POLLIN) {
                    while (auto f = can->next()) pipe.process(*f);
                }
                if (p.revents & (POLLERR | POLLHUP | POLLNVAL)) {
                    std::cerr << "n2kd: CAN socket error on " << *opts_.canInterface << ", reopening\n";
                    can.reset();
                    nextRetry = Steady::now() + std::chrono::duration_cast<Steady::duration>(
                                                    std::chrono::duration<double>(kCanRetrySeconds));
                }
            } else if (pub && p.fd == pub->fd() && (p.revents & POLLIN)) {
                pub->acceptPending();
            }
        }
        double now = wallNow();
        if (pipe.tickDue(now)) pipe.tick(now);
    }
    pipe.summary(0);
    return 0;
}

}  // namespace n2k
