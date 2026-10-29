#pragma once
#include <optional>

#include "n2k/Frame.h"

namespace n2k {

struct FrameSource {
    virtual ~FrameSource() = default;
    // nullopt = end of stream (file) or no frame yet (live)
    virtual std::optional<CanFrame> next() = 0;
};

}  // namespace n2k
