#pragma once
#include <cstddef>
#include <istream>
#include <optional>
#include <string_view>

#include "n2k/FrameSource.h"

namespace n2k {

class LogFileSource : public FrameSource {
public:
    explicit LogFileSource(std::istream& in);
    std::optional<CanFrame> next() override;
    size_t skippedLines() const { return skipped_; }
    static std::optional<CanFrame> parseLine(std::string_view line);  // exposed for tests

private:
    std::istream& in_;
    size_t skipped_ = 0;
};

}  // namespace n2k
