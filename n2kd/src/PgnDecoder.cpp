#include "n2k/PgnDecoder.h"

#include <cmath>

namespace n2k {

namespace {

// Little-endian bit order: bit N of the message is bit (N % 8) of byte (N / 8).
uint64_t readBits(const std::vector<uint8_t>& p, int offset, int length) {
    uint64_t v = 0;
    for (int i = 0; i < length; ++i) {
        int bit = offset + i;
        if ((p[bit / 8] >> (bit % 8)) & 1u) v |= (uint64_t{1} << i);
    }
    return v;
}

int64_t signExtend(uint64_t raw, int length) {
    if (length < 64 && ((raw >> (length - 1)) & 1u)) raw |= ~uint64_t{0} << length;
    return static_cast<int64_t>(raw);
}

bool isNumeric(const std::string& t) {
    return t == "NUMBER" || t == "DATE" || t == "TIME" || t == "DURATION" || t == "MMSI";
}

std::string trimString(const std::vector<uint8_t>& p, int byteOffset, int byteLen) {
    int end = byteLen;
    while (end > 0) {
        uint8_t c = p[byteOffset + end - 1];
        if (c == 0xFF || c == 0x00 || c == '@' || c == ' ') --end;
        else break;
    }
    return std::string(reinterpret_cast<const char*>(p.data()) + byteOffset, static_cast<size_t>(end));
}

}  // namespace

std::optional<DecodedMessage> PgnDecoder::decode(const N2kMessage& m) const {
    const PgnDef* def = db_.find(m.header.pgn);
    if (!def) return std::nullopt;

    DecodedMessage out{m.header.pgn, m.header.source, m.timestamp, def->id, {}};
    const int totalBits = static_cast<int>(m.payload.size()) * 8;

    for (const FieldDef& f : def->fields) {
        if (f.id.empty() || f.bitLength <= 0) continue;
        if (f.bitOffset + f.bitLength > totalBits) continue;

        const bool numeric = isNumeric(f.fieldType);
        const bool lookup = f.fieldType == "LOOKUP" || f.fieldType == "INDIRECT_LOOKUP";

        if (f.fieldType == "STRING_FIX") {
            if (f.bitOffset % 8 != 0 || f.bitLength % 8 != 0) continue;
            out.fields.emplace(f.id, trimString(m.payload, f.bitOffset / 8, f.bitLength / 8));
            continue;
        }
        if ((!numeric && !lookup) || f.bitLength > 64) continue;

        const uint64_t raw = readBits(m.payload, f.bitOffset, f.bitLength);
        const int64_t sval = f.isSigned ? signExtend(raw, f.bitLength) : static_cast<int64_t>(raw);
        const double value = (f.isSigned ? static_cast<double>(sval) : static_cast<double>(raw)) * f.resolution;

        bool na;
        if (f.rangeMin || f.rangeMax) {
            // Tolerate floating point noise at the range boundary.
            const double tol = std::abs(f.resolution) * 0.5;
            na = (f.rangeMax && value > *f.rangeMax + tol) || (f.rangeMin && value < *f.rangeMin - tol);
        } else if (f.bitLength == 1) {
            na = false;
        } else if (f.isSigned) {
            na = raw == (uint64_t{1} << (f.bitLength - 1)) - 1;
        } else {
            na = f.bitLength == 64 ? raw == ~uint64_t{0} : raw == (uint64_t{1} << f.bitLength) - 1;
        }
        if (na) {
            out.fields.emplace(f.id, std::monostate{});
            continue;
        }

        if (lookup) {
            out.fields.emplace(f.id, sval);
            if (f.fieldType == "LOOKUP" && f.lookup) {
                if (auto name = db_.lookupName(*f.lookup, sval)) out.fields.emplace(f.id + "Name", *name);
            }
        } else if (f.fieldType == "MMSI" || f.resolution == 1.0) {
            out.fields.emplace(f.id, sval);
        } else {
            out.fields.emplace(f.id, value);
        }
    }
    return out;
}

}  // namespace n2k
