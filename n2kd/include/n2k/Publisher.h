#pragma once
#include <cstddef>
#include <expected>
#include <filesystem>
#include <nlohmann/json.hpp>
#include <string>
#include <utility>
#include <vector>

namespace n2k {

// Unix stream socket publisher: newline-delimited JSON to every connected client.
// Each client has a bounded output queue: bytes the socket does not accept at once
// wait in it and are retried by later broadcasts and flushPending().
class Publisher {
public:
    static constexpr size_t kMaxPendingBytes = 4 * 1024 * 1024;  // per client; exceeding it drops the client
    static constexpr int kSendBufferBytes = 1024 * 1024;         // SO_SNDBUF requested for accepted clients

    // Unlinks any stale socket file first; creates the socket with mode 0660.
    static std::expected<Publisher, std::string> listen(const std::filesystem::path& socketPath);

    Publisher(const Publisher&) = delete;
    Publisher& operator=(const Publisher&) = delete;
    Publisher(Publisher&& o) noexcept;
    Publisher& operator=(Publisher&& o) noexcept;
    ~Publisher();

    int fd() const { return fd_; }  // listening fd for poll()
    void acceptPending();           // accept all waiting clients, queue helloMessage() to each
    // One line per message, queued behind any bytes still pending for that client.
    // A client is dropped only on a hard send error or when its queue would exceed
    // kMaxPendingBytes, never because the socket is merely full.
    void broadcast(const nlohmann::json& msg);
    // Retries pending bytes for every client (call when POLLOUT fires and each tick).
    void flushPending();
    // Fds of clients that have pending bytes: poll these for POLLOUT.
    std::vector<int> clientFds() const;
    size_t clientCount() const { return clients_.size(); }

private:
    struct Client {
        int fd;
        std::string pending;  // queued bytes not yet accepted by the socket
    };

    Publisher(int fd, std::filesystem::path path) : fd_(fd), path_(std::move(path)) {}
    void closeAll() noexcept;
    // Sends pending bytes, then `line` (may be empty). False if the client must be dropped.
    static bool push(Client& c, const std::string& line);

    int fd_ = -1;
    std::filesystem::path path_;
    std::vector<Client> clients_;
};

}  // namespace n2k
