#include "n2k/RawLogger.h"

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <iostream>
#include <system_error>
#include <utility>
#include <vector>

namespace n2k {

RawLogger::RawLogger(std::filesystem::path dir, std::string ifname, uintmax_t maxBytesPerFile, unsigned maxFiles)
    : dir_(std::move(dir)), ifname_(std::move(ifname)), maxBytes_(maxBytesPerFile), maxFiles_(maxFiles) {}

bool RawLogger::openNew() {
    out_.close();
    out_.clear();
    written_ = 0;
    std::error_code ec;
    std::filesystem::create_directories(dir_, ec);
    std::time_t now = std::time(nullptr);
    std::tm tm{};
    gmtime_r(&now, &tm);
    char name[64];
    std::snprintf(name, sizeof name, "n2k-%04d%02d%02d-%02d%02d%02d-%03u.log", tm.tm_year + 1900, tm.tm_mon + 1,
                  tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec, ++seq_);
    out_.open(dir_ / name, std::ios::out | std::ios::app);
    if (!out_) {
        if (!warnedOpen_) std::cerr << "n2kd: raw log: cannot open " << (dir_ / name) << "\n";
        warnedOpen_ = true;
        return false;
    }
    pruneOld();
    return true;
}

void RawLogger::pruneOld() {
    std::error_code ec;
    std::vector<std::filesystem::path> files;
    for (std::filesystem::directory_iterator it(dir_, ec), end; !ec && it != end; it.increment(ec)) {
        auto n = it->path().filename().string();
        if (n.rfind("n2k-", 0) == 0 && it->path().extension() == ".log") files.push_back(it->path());
    }
    std::sort(files.begin(), files.end());
    for (size_t i = 0; files.size() - i > maxFiles_; ++i) std::filesystem::remove(files[i], ec);
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
