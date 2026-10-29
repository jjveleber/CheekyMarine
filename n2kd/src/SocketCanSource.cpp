#include "n2k/SocketCanSource.h"

#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <utility>

namespace n2k {

namespace {
std::string errText(std::string_view ifname, const char* what) {
    int e = errno;
    return std::string(what) + " " + std::string(ifname) + ": " + std::strerror(e);
}
}  // namespace

std::expected<SocketCanSource, std::string> SocketCanSource::open(std::string_view ifname) {
    if (ifname.size() >= IFNAMSIZ) {
        return std::unexpected("interface name too long: " + std::string(ifname));
    }
    int fd = ::socket(PF_CAN, SOCK_RAW | SOCK_NONBLOCK, CAN_RAW);
    if (fd < 0) return std::unexpected(errText(ifname, "socket for"));
    SocketCanSource src(fd);  // closes fd on any early return

    ifreq ifr{};
    std::memcpy(ifr.ifr_name, ifname.data(), ifname.size());
    if (::ioctl(fd, SIOCGIFINDEX, &ifr) < 0) return std::unexpected(errText(ifname, "ioctl SIOCGIFINDEX on"));

    sockaddr_can addr{};
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;
    if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        return std::unexpected(errText(ifname, "bind to"));
    }

    int on = 1;
    if (::setsockopt(fd, SOL_SOCKET, SO_TIMESTAMP, &on, sizeof(on)) < 0) {
        return std::unexpected(errText(ifname, "setsockopt SO_TIMESTAMP on"));
    }
    return src;
}

SocketCanSource::SocketCanSource(SocketCanSource&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}

SocketCanSource& SocketCanSource::operator=(SocketCanSource&& o) noexcept {
    if (this != &o) {
        if (fd_ >= 0) ::close(fd_);
        fd_ = std::exchange(o.fd_, -1);
    }
    return *this;
}

SocketCanSource::~SocketCanSource() {
    if (fd_ >= 0) ::close(fd_);
}

std::optional<CanFrame> SocketCanSource::next() {
    for (;;) {
        can_frame cf{};
        iovec iov{&cf, sizeof(cf)};
        alignas(cmsghdr) char ctrl[CMSG_SPACE(sizeof(timeval))];
        msghdr msg{};
        msg.msg_iov = &iov;
        msg.msg_iovlen = 1;
        msg.msg_control = ctrl;
        msg.msg_controllen = sizeof(ctrl);

        ssize_t n = ::recvmsg(fd_, &msg, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return std::nullopt;  // EAGAIN/EWOULDBLOCK or real error
        }
        if (n < static_cast<ssize_t>(sizeof(can_frame))) continue;
        if (!(cf.can_id & CAN_EFF_FLAG)) continue;
        if (cf.can_id & (CAN_RTR_FLAG | CAN_ERR_FLAG)) continue;

        CanFrame out{};
        out.id = cf.can_id & CAN_EFF_MASK;
        out.len = std::min<uint8_t>(cf.can_dlc, 8);
        for (uint8_t i = 0; i < out.len; ++i) out.data[i] = cf.data[i];

        bool haveTs = false;
        for (cmsghdr* c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
            if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_TIMESTAMP) {
                timeval tv;
                std::memcpy(&tv, CMSG_DATA(c), sizeof(tv));
                out.timestamp = static_cast<double>(tv.tv_sec) + static_cast<double>(tv.tv_usec) * 1e-6;
                haveTs = true;
                break;
            }
        }
        if (!haveTs) {
            timespec ts;
            ::clock_gettime(CLOCK_REALTIME, &ts);
            out.timestamp = static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
        }
        return out;
    }
}

bool SocketCanSource::send(const CanFrame& f) {
    can_frame cf{};
    cf.can_id = (f.id & CAN_EFF_MASK) | CAN_EFF_FLAG;
    cf.can_dlc = std::min<uint8_t>(f.len, 8);
    for (uint8_t i = 0; i < cf.can_dlc; ++i) cf.data[i] = f.data[i];
    return ::write(fd_, &cf, sizeof(cf)) == static_cast<ssize_t>(sizeof(cf));
}

}  // namespace n2k
