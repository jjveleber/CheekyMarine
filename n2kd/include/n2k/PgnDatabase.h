#pragma once
#include <cstdint>
#include <expected>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace n2k {

struct FieldDef {
    std::string id;
    int bitOffset = 0;
    int bitLength = 0;
    double resolution = 1.0;
    bool isSigned = false;
    std::string fieldType;
    std::optional<std::string> lookup;
    std::optional<double> rangeMin, rangeMax;
};

struct PgnDef {
    uint32_t pgn = 0;
    std::string id;
    bool fastPacket = false;
    std::vector<FieldDef> fields;
};

class PgnDatabase {
public:
    static std::expected<PgnDatabase, std::string> load(const std::filesystem::path& canboatJson);
    // First definition for that PGN; nullptr if unknown.
    const PgnDef* find(uint32_t pgn) const;
    // Unknown PGNs: true if pgn >= 0x1F000 (standard rule), else false.
    bool isFastPacket(uint32_t pgn) const;
    std::optional<std::string> lookupName(const std::string& enumeration, int64_t value) const;

private:
    std::map<uint32_t, PgnDef> pgns_;
    std::map<std::string, std::map<int64_t, std::string>> enums_;
};

}  // namespace n2k
