#pragma once
#include <expected>
#include <optional>
#include <string>
#include <string_view>

#include "n2k/Frame.h"
#include "n2k/FrameSource.h"

namespace n2k {

// Non-blocking SocketCAN reader/writer for 29-bit (NMEA 2000) frames.
class SocketCanSource : public FrameSource {
public:
    static std::expected<SocketCanSource, std::string> open(std::string_view ifname);

    SocketCanSource(const SocketCanSource&) = delete;
    SocketCanSource& operator=(const SocketCanSource&) = delete;
    SocketCanSource(SocketCanSource&& o) noexcept;
    SocketCanSource& operator=(SocketCanSource&& o) noexcept;
    ~SocketCanSource() override;

    // Non-blocking read; nullopt if nothing pending (or on error).
    std::optional<CanFrame> next() override;
    int fd() const { return fd_; }
    bool send(const CanFrame& f);

private:
    explicit SocketCanSource(int fd) : fd_(fd) {}
    int fd_ = -1;
};

}  // namespace n2k
