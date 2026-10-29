#include "n2k/AddressClaim.h"

namespace n2k {

CanFrame buildAddressClaim(const AddressClaimConfig& c) {
    auto put = [](uint64_t v, unsigned bits) { return v & ((uint64_t{1} << bits) - 1); };
    uint64_t v = 0;
    v |= put(c.uniqueNumber, 21);
    v |= put(c.manufacturerCode, 11) << 21;
    v |= put(c.deviceInstanceLower, 3) << 32;
    v |= put(c.deviceInstanceUpper, 5) << 35;
    v |= put(c.deviceFunction, 8) << 40;
    v |= uint64_t{1} << 48;  // reserved bit, set to 1
    v |= put(c.deviceClass, 7) << 49;
    v |= put(c.systemInstance, 4) << 56;
    v |= put(c.industryGroup, 3) << 60;
    v |= put(c.arbitraryAddressCapable, 1) << 63;

    CanFrame f{makeCanId(6, 60928, c.sourceAddress, 0xFF), 8, {}, 0};
    for (unsigned i = 0; i < 8; ++i) f.data[i] = static_cast<uint8_t>(v >> (8 * i));
    return f;
}

}  // namespace n2k
