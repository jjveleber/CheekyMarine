#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <variant>

#include "n2k/FastPacket.h"
#include "n2k/PgnDatabase.h"

namespace n2k {

using FieldValue = std::variant<std::monostate, double, int64_t, std::string>;  // monostate = not available

struct DecodedMessage {
    uint32_t pgn;
    uint8_t source;
    double timestamp;
    std::string pgnId;
    std::map<std::string, FieldValue> fields;
};

class PgnDecoder {
public:
    explicit PgnDecoder(const PgnDatabase& db) : db_(db) {}
    std::optional<DecodedMessage> decode(const N2kMessage& m) const;  // nullopt for unknown PGNs

private:
    const PgnDatabase& db_;
};

}  // namespace n2k
