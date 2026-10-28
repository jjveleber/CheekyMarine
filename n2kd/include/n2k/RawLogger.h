#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>

#include "n2k/Frame.h"

namespace n2k {

// Writes frames in candump -L format (replayable by LogFileSource) to
// n2k-YYYYMMDD-HHMMSS-NNN.log files in dir, rotating by size and deleting the
// oldest files beyond maxFiles. I/O failures never throw.
class RawLogger {
public:
    RawLogger(std::filesystem::path dir, std::string ifname, uintmax_t maxBytesPerFile = 50 * 1024 * 1024,
              unsigned maxFiles = 20);
    void write(const CanFrame& f);
    void flush();

private:
    bool openNew();
    void pruneOld();

    std::filesystem::path dir_;
    std::string ifname_;
    uintmax_t maxBytes_;
    unsigned maxFiles_;
    unsigned seq_ = 0;
    uintmax_t written_ = 0;
    std::ofstream out_;
    bool warnedOpen_ = false;
    bool warnedWrite_ = false;
};

}  // namespace n2k
