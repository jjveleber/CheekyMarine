#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include <utility>

namespace n2k {

template <class T> struct Aged {
    std::optional<T> value;
    double updatedAt = 0;  // epoch s
    void set(T v, double now) { value = v; updatedAt = now; }
    bool fresh(double now, double maxAge) const { return value && now - updatedAt <= maxAge; }
};

struct VesselState {
    Aged<std::pair<double, double>> position;  // lat, lon degrees
    Aged<double> sog;                          // m/s
    Aged<double> cog;                          // rad, true
    Aged<double> heading;                      // rad
    Aged<std::string> headingReference;        // "True" | "Magnetic"
    Aged<double> depth;                        // m, below transducer
    Aged<double> depthOffset;                  // m, + = to waterline, - = to keel
    Aged<double> stw;                          // m/s
    Aged<double> waterTemp;                    // K
    Aged<double> gnssTime;                     // epoch s from 126992 or 129029
    Aged<int64_t> satellites;
    Aged<double> engineRpm;                    // optional, 127488 instance 0
};

}  // namespace n2k
