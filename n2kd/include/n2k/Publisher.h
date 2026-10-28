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
class Publisher {
public:
    // Unlinks any stale socket file first; creates the socket with mode 0660.
    static std::expected<Publisher, std::string> listen(const std::filesystem::path& socketPath);

    Publisher(const Publisher&) = delete;
    Publisher& operator=(const Publisher&) = delete;
    Publisher(Publisher&& o) noexcept;
    Publisher& operator=(Publisher&& o) noexcept;
    ~Publisher();

    int fd() const { return fd_; }  // listening fd for poll()
    void acceptPending();           // accept all waiting clients, send helloMessage() to each
    // One line per message. Clients whose send fails or would block are dropped.
    void broadcast(const nlohmann::json& msg);
    size_t clientCount() const { return clients_.size(); }

private:
    Publisher(int fd, std::filesystem::path path) : fd_(fd), path_(std::move(path)) {}
    void closeAll() noexcept;

    int fd_ = -1;
    std::filesystem::path path_;
    std::vector<int> clients_;
};

}  // namespace n2k
