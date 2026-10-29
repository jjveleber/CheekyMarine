#include "n2k/RawLogger.h"

#include <algorithm>
#include <charconv>
#include <cstdio>
#include <ctime>
#include <iostream>
#include <system_error>
#include <utility>
#include <vector>

namespace n2k {
namespace {

// Parses "n2k-<seq>-YYYYMMDD-HHMMSS.log" (seq is 6 or more digits); 0 when the name does not match.
unsigned parseSeq(const std::string& n) {
    if (n.rfind("n2k-", 0) != 0) return 0;
    auto dash = n.find('-', 4);
    if (dash == std::string::npos || dash - 4 < 6) return 0;
    std::string_view tail(n.data() + dash, n.size() - dash);
    if (tail.size() != std::string_view("-YYYYMMDD-HHMMSS.log").size() || tail[9] != '-' || !tail.ends_with(".log"))
        return 0;
    for (size_t i : {1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15})
        if (tail[i] < '0' || tail[i] > '9') return 0;
    unsigned seq = 0;
    auto [p, ec] = std::from_chars(n.data() + 4, n.data() + dash, seq);
    return ec == std::errc{} && p == n.data() + dash ? seq : 0;
}

// Log files in dir with their sequence numbers, lowest sequence first.
std::vector<std::pair<unsigned, std::filesystem::path>> logFiles(const std::filesystem::path& dir) {
    std::error_code ec;
    std::vector<std::pair<unsigned, std::filesystem::path>> files;
    for (std::filesystem::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec)) {
        if (unsigned s = parseSeq(it->path().filename().string())) files.emplace_back(s, it->path());
    }
    std::sort(files.begin(), files.end());
    return files;
}

}  // namespace

RawLogger::RawLogger(std::filesystem::path dir, std::string ifname, uintmax_t maxBytesPerFile, unsigned maxFiles)
    : dir_(std::move(dir)), ifname_(std::move(ifname)), maxBytes_(maxBytesPerFile), maxFiles_(maxFiles) {
    auto files = logFiles(dir_);
    if (!files.empty()) seq_ = files.back().first;
}

bool RawLogger::openNew() {
    out_.close();
    out_.clear();
    written_ = 0;
    std::error_code ec;
    std::filesystem::create_directories(dir_, ec);
    std::time_t now = std::time(nullptr);
    std::tm tm{};
    gmtime_r(&now, &tm);
    // The sequence leads the name so ordering never depends on the wall clock; noreplace never reuses a file.
    std::filesystem::path path;
    for (int attempt = 0; attempt < 100; ++attempt) {
        char name[64];
        std::snprintf(name, sizeof name, "n2k-%06u-%04d%02d%02d-%02d%02d%02d.log", ++seq_, tm.tm_year + 1900,
                      tm.tm_mon + 1, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec);
        path = dir_ / name;
        out_.clear();
        out_.open(path, std::ios::out | std::ios::noreplace);
        if (out_.is_open()) break;
        if (!std::filesystem::exists(path, ec)) {  // a real failure, not a name collision
            --seq_;
            break;
        }
    }
    if (!out_.is_open()) {
        if (!warnedOpen_) std::cerr << "n2kd: raw log: cannot open " << path << "\n";
        warnedOpen_ = true;
        return false;
    }
    current_ = path;
    pruneOld();
    return true;
}

void RawLogger::pruneOld() {
    std::error_code ec;
    auto files = logFiles(dir_);
    for (size_t i = 0; files.size() - i > maxFiles_; ++i) {
        if (files[i].second != current_) std::filesystem::remove(files[i].second, ec);
    }
}

void RawLogger::write(const CanFrame& f) {
    char line[96];
    int n = std::snprintf(line, sizeof line, "(%.6f) %s %08X#", f.timestamp, ifname_.c_str(), f.id);
    if (n < 0 || static_cast<size_t>(n) >= sizeof line - 20) return;
    for (unsigned i = 0; i < f.len && i < 8; ++i) n += std::snprintf(line + n, sizeof line - n, "%02X", f.data[i]);
    line[n++] = '\n';

    if (!out_.is_open() || (written_ > 0 && written_ + n > maxBytes_)) {
        if (!openNew()) return;
    }
    out_.write(line, n);
    if (!out_) {
        if (!warnedWrite_) std::cerr << "n2kd: raw log: write failed\n";
        warnedWrite_ = true;
        out_.clear();
        return;
    }
    written_ += n;
}

void RawLogger::flush() {
    if (out_.is_open()) out_.flush();
}

}  // namespace n2k
