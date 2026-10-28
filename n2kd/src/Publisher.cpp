#include "n2k/Publisher.h"

#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <utility>

#include "n2k/Json.h"

namespace n2k {

namespace {
std::string errText(const std::filesystem::path& p, const char* what) {
    int e = errno;
    return std::string(what) + " " + p.string() + ": " + std::strerror(e);
}

// Sends as much of [data, data + size) as the socket accepts without blocking.
// Returns the byte count sent, or -1 on a hard error (anything but EAGAIN or EINTR).
ssize_t sendSome(int fd, const char* data, size_t size) {
    size_t sent = 0;
    while (sent < size) {
        ssize_t n = ::send(fd, data + sent, size - sent, MSG_NOSIGNAL | MSG_DONTWAIT);
        if (n > 0) {
            sent += static_cast<size_t>(n);
            continue;
        }
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
        return -1;
    }
    return static_cast<ssize_t>(sent);
}
}  // namespace

bool Publisher::push(Client& c, const std::string& line) {
    if (!c.pending.empty()) {
        ssize_t n = sendSome(c.fd, c.pending.data(), c.pending.size());
        if (n < 0) return false;
        c.pending.erase(0, static_cast<size_t>(n));
    }
    size_t offset = 0;
    if (c.pending.empty() && !line.empty()) {
        ssize_t n = sendSome(c.fd, line.data(), line.size());
        if (n < 0) return false;
        offset = static_cast<size_t>(n);
    }
    const size_t rest = line.size() - offset;
    if (c.pending.size() + rest > kMaxPendingBytes) return false;
    c.pending.append(line, offset, rest);
    return true;
}

std::expected<Publisher, std::string> Publisher::listen(const std::filesystem::path& socketPath) {
    sockaddr_un addr{};
    if (socketPath.native().size() > sizeof(addr.sun_path) - 1) {
        return std::unexpected("socket path too long: " + socketPath.string());
    }
    int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) return std::unexpected(errText(socketPath, "socket for"));
    Publisher pub(fd, std::filesystem::path{});  // closes fd on early return; path unset until bound

    if (::unlink(socketPath.c_str()) < 0 && errno != ENOENT) return std::unexpected(errText(socketPath, "unlink"));
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, socketPath.c_str(), socketPath.native().size());
    if (::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        return std::unexpected(errText(socketPath, "bind"));
    }
    pub.path_ = socketPath;  // we created the file: unlink on destruction
    if (::chmod(socketPath.c_str(), 0660) < 0) return std::unexpected(errText(socketPath, "chmod"));
    if (::listen(fd, 8) < 0) return std::unexpected(errText(socketPath, "listen on"));
    return pub;
}

Publisher::Publisher(Publisher&& o) noexcept
    : fd_(std::exchange(o.fd_, -1)), path_(std::move(o.path_)), clients_(std::move(o.clients_)) {
    o.path_.clear();
    o.clients_.clear();
}

Publisher& Publisher::operator=(Publisher&& o) noexcept {
    if (this != &o) {
        closeAll();
        fd_ = std::exchange(o.fd_, -1);
        path_ = std::move(o.path_);
        clients_ = std::move(o.clients_);
        o.path_.clear();
        o.clients_.clear();
    }
    return *this;
}

Publisher::~Publisher() { closeAll(); }

void Publisher::closeAll() noexcept {
    for (const Client& c : clients_) ::close(c.fd);
    clients_.clear();
    if (fd_ >= 0) ::close(fd_);
    fd_ = -1;
    if (!path_.empty()) ::unlink(path_.c_str());
    path_.clear();
}

void Publisher::acceptPending() {
    if (fd_ < 0) return;
    const std::string hello = helloMessage().dump() + "\n";
    for (;;) {
        int c = ::accept4(fd_, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
        if (c < 0) {
            if (errno == EINTR || errno == ECONNABORTED) continue;
            return;  // EAGAIN or a real error: nothing more to accept now
        }
        int sndbuf = kSendBufferBytes;
        ::setsockopt(c, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf));  // best effort
        Client client{c, {}};
        if (push(client, hello)) {
            clients_.push_back(std::move(client));
        } else {
            ::close(c);
        }
    }
}

void Publisher::broadcast(const nlohmann::json& msg) {
    const std::string line = msg.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) + "\n";
    std::erase_if(clients_, [&](Client& c) {
        if (push(c, line)) return false;
        ::close(c.fd);
        return true;
    });
}

void Publisher::flushPending() {
    const std::string none;
    std::erase_if(clients_, [&](Client& c) {
        if (c.pending.empty() || push(c, none)) return false;
        ::close(c.fd);
        return true;
    });
}

std::vector<int> Publisher::clientFds() const {
    std::vector<int> fds;
    for (const Client& c : clients_) {
        if (!c.pending.empty()) fds.push_back(c.fd);
    }
    return fds;
}

}  // namespace n2k
