#pragma once
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

inline std::filesystem::path tmpSock() {
    static std::atomic<int> counter{0};
    return std::filesystem::temp_directory_path() /
           ("n2kd-test-" + std::to_string(::getpid()) + "-" + std::to_string(counter++) + ".sock");
}

inline sockaddr_un makeAddr(const std::filesystem::path& path) {
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    return addr;
}

// Returns a connected blocking fd, or -1 on failure.
inline int connectUnix(const std::filesystem::path& path) {
    int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    sockaddr_un addr = makeAddr(path);
    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(fd);
        return -1;
    }
    return fd;
}

// Reads until n newline-terminated lines have arrived or the timeout expires.
inline std::vector<std::string> readLines(int fd, size_t n, double timeoutSeconds = 1.0) {
    std::vector<std::string> lines;
    std::string buf;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::duration<double>(timeoutSeconds);
    while (lines.size() < n) {
        auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now());
        if (left.count() <= 0) break;
        pollfd p{fd, POLLIN, 0};
        if (::poll(&p, 1, static_cast<int>(left.count())) <= 0) break;
        char tmp[4096];
        ssize_t r = ::read(fd, tmp, sizeof(tmp));
        if (r <= 0) break;
        buf.append(tmp, static_cast<size_t>(r));
        size_t pos;
        while (lines.size() < n && (pos = buf.find('\n')) != std::string::npos) {
            lines.push_back(buf.substr(0, pos));
            buf.erase(0, pos + 1);
        }
    }
    return lines;
}

// Leaves a stale socket file at path.
inline void bindAndAbandon(const std::filesystem::path& path) {
    int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
    sockaddr_un addr = makeAddr(path);
    ::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr));
    ::close(fd);
}
