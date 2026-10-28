#pragma once
#include <cstdint>

#include "n2k/Frame.h"

namespace n2k {

struct AddressClaimConfig {
    uint32_t uniqueNumber;                // 21 bits
    uint16_t manufacturerCode = 2046;     // 11 bits; not assigned to any maker in canboat MANUFACTURER_CODE (verified 2026-10-28); NMEA assigns real codes to members, we are not one
    uint8_t deviceFunction = 130;         // Display
    uint8_t deviceClass = 120;            // Display
    uint8_t industryGroup = 4;            // Marine
    uint8_t sourceAddress = 0xFE;
    uint8_t deviceInstanceLower = 0;      // 3 bits
    uint8_t deviceInstanceUpper = 0;      // 5 bits
    uint8_t systemInstance = 0;           // 4 bits
    uint8_t arbitraryAddressCapable = 1;  // 1 bit
};

// PGN 60928, priority 6, destination 0xFF, 8 bytes per canboat field table.
CanFrame buildAddressClaim(const AddressClaimConfig& c);

}  // namespace n2k
