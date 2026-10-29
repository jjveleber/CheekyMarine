#include "n2k/PgnDatabase.h"

#include <cmath>
#include <fstream>

#include <nlohmann/json.hpp>

namespace n2k {

using nlohmann::json;

namespace {

std::string strOr(const json& j, const char* key) {
    auto it = j.find(key);
    return (it != j.end() && it->is_string()) ? it->get<std::string>() : std::string();
}

std::optional<double> numOpt(const json& j, const char* key) {
    auto it = j.find(key);
    if (it == j.end() || !it->is_number()) return std::nullopt;
    return it->get<double>();
}

FieldDef parseField(const json& f) {
    FieldDef d;
    d.id = strOr(f, "Id");
    // Fields without BitOffset/BitLength, or with out-of-bounds values, keep bitLength 0 and are skipped by the decoder.
    constexpr double kMaxBits = 8.0 * 1785;
    auto off = numOpt(f, "BitOffset");
    auto len = numOpt(f, "BitLength");
    if (off && len && *off >= 0 && *len > 0 && *off == std::floor(*off) && *len == std::floor(*len) &&
        *off + *len <= kMaxBits) {
        d.bitOffset = static_cast<int>(*off);
        d.bitLength = static_cast<int>(*len);
    }
    d.resolution = numOpt(f, "Resolution").value_or(1.0);
    auto s = f.find("Signed");
    d.isSigned = s != f.end() && s->is_boolean() && s->get<bool>();
    d.fieldType = strOr(f, "FieldType");
    auto l = f.find("LookupEnumeration");
    if (l != f.end() && l->is_string()) d.lookup = l->get<std::string>();
    d.rangeMin = numOpt(f, "RangeMin");
    d.rangeMax = numOpt(f, "RangeMax");
    return d;
}

}  // namespace

std::expected<PgnDatabase, std::string> PgnDatabase::load(const std::filesystem::path& canboatJson) {
    std::ifstream in(canboatJson);
    if (!in) return std::unexpected("cannot open " + canboatJson.string());
    json root = json::parse(in, nullptr, false);
    if (root.is_discarded() || !root.is_object()) return std::unexpected("cannot parse " + canboatJson.string());

    PgnDatabase db;
    if (auto it = root.find("LookupEnumerations"); it != root.end() && it->is_array()) {
        for (const auto& e : *it) {
            std::string name = strOr(e, "Name");
            auto vals = e.find("EnumValues");
            if (name.empty() || vals == e.end() || !vals->is_array()) continue;
            auto& m = db.enums_[name];
            for (const auto& v : *vals) {
                auto val = numOpt(v, "Value");
                if (val) m.emplace(static_cast<int64_t>(*val), strOr(v, "Name"));
            }
        }
    }
    if (auto it = root.find("PGNs"); it != root.end() && it->is_array()) {
        for (const auto& p : *it) {
            auto num = numOpt(p, "PGN");
            if (!num) continue;
            PgnDef def;
            def.pgn = static_cast<uint32_t>(*num);
            if (db.pgns_.count(def.pgn)) continue;  // keep first definition
            def.id = strOr(p, "Id");
            def.fastPacket = strOr(p, "Type") == "Fast";
            auto fields = p.find("Fields");
            if (fields != p.end() && fields->is_array()) {
                for (const auto& f : *fields) def.fields.push_back(parseField(f));
            }
            db.pgns_.emplace(def.pgn, std::move(def));
        }
    }
    return db;
}

const PgnDef* PgnDatabase::find(uint32_t pgn) const {
    auto it = pgns_.find(pgn);
    return it == pgns_.end() ? nullptr : &it->second;
}

bool PgnDatabase::isFastPacket(uint32_t pgn) const {
    if (const PgnDef* d = find(pgn)) return d->fastPacket;
    return pgn >= 0x1F000;
}

std::optional<std::string> PgnDatabase::lookupName(const std::string& enumeration, int64_t value) const {
    auto e = enums_.find(enumeration);
    if (e == enums_.end()) return std::nullopt;
    auto v = e->second.find(value);
    if (v == e->second.end()) return std::nullopt;
    return v->second;
}

}  // namespace n2k
