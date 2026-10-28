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

// True if the whole line was sent without blocking.
bool sendAll(int fd, const std::string& line) {
    ssize_t n = ::send(fd, line.data(), line.size(), MSG_NOSIGNAL | MSG_DONTWAIT);
    return n >= 0 && static_cast<size_t>(n) == line.size();
}
}  // namespace

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
    for (int c : clients_) ::close(c);
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
        if (sendAll(c, hello)) {
            clients_.push_back(c);
        } else {
            ::close(c);
        }
    }
}

void Publisher::broadcast(const nlohmann::json& msg) {
    const std::string line = msg.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace) + "\n";
    std::erase_if(clients_, [&](int c) {
        if (sendAll(c, line)) return false;
        ::close(c);
        return true;
    });
}

}  // namespace n2k
