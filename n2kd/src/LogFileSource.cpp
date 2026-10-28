#include "n2k/LogFileSource.h"

#include <charconv>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <string>
#include <vector>

namespace n2k {
namespace {

constexpr double kMaxTimestamp = 4e9;  // epoch s, year 2096

std::string_view trim(std::string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\r')) s.remove_suffix(1);
    return s;
}

template <typename T>
bool parseNum(std::string_view s, T& out, int base = 10) {
    if (s.empty()) return false;
    auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), out, base);
    return ec == std::errc{} && p == s.data() + s.size();
}

bool parseDouble(std::string_view s, double& out) {
    if (s.empty()) return false;
    std::string tmp(s);
    char* end = nullptr;
    out = std::strtod(tmp.c_str(), &end);
    return end == tmp.c_str() + tmp.size() && std::isfinite(out);
}

std::optional<CanFrame> parseCandump(std::string_view line) {
    // (secs.usecs) iface ID#DATA
    if (line.empty() || line.front() != '(') return std::nullopt;
    auto close = line.find(')');
    if (close == std::string_view::npos) return std::nullopt;
    double ts;
    if (!parseDouble(line.substr(1, close - 1), ts)) return std::nullopt;
    auto rest = trim(line.substr(close + 1));
    auto sp = rest.find_first_of(" \t");
    if (sp == std::string_view::npos) return std::nullopt;  // interface token ignored
    rest = trim(rest.substr(sp));
    auto hash = rest.find('#');
    if (hash == std::string_view::npos) return std::nullopt;
    uint32_t id;
    if (!parseNum(rest.substr(0, hash), id, 16)) return std::nullopt;
    auto hex = rest.substr(hash + 1);
    if (hex.size() % 2 != 0 || hex.size() > 16) return std::nullopt;
    CanFrame f{id & 0x1FFFFFFFu, static_cast<uint8_t>(hex.size() / 2), {}, ts};
    for (size_t i = 0; i < hex.size() / 2; ++i) {
        if (!parseNum(hex.substr(i * 2, 2), f.data[i], 16)) return std::nullopt;
    }
    return f;
}

bool parseTimestamp(std::string_view s, double& out) {
    // 2011-04-25-10:16:42.554 or 2020-08-22T13:52:52.882Z
    if (!s.empty() && s.back() == 'Z') s.remove_suffix(1);
    if (s.size() < 19) return false;
    if (s[4] != '-' || s[7] != '-' || (s[10] != '-' && s[10] != 'T') || s[13] != ':' || s[16] != ':') {
        return false;
    }
    int v[6];
    const size_t pos[6] = {0, 5, 8, 11, 14, 17};
    const size_t len[6] = {4, 2, 2, 2, 2, 2};
    for (int i = 0; i < 6; ++i) {
        if (!parseNum(s.substr(pos[i], len[i]), v[i])) return false;
    }
    double frac = 0;
    if (s.size() > 19) {
        if (s[19] != '.' || !parseDouble(s.substr(19), frac)) return false;
    }
    std::tm tm{};
    tm.tm_year = v[0] - 1900;
    tm.tm_mon = v[1] - 1;
    tm.tm_mday = v[2];
    tm.tm_hour = v[3];
    tm.tm_min = v[4];
    tm.tm_sec = v[5];
    out = static_cast<double>(timegm(&tm)) + frac;
    return true;
}

std::optional<CanFrame> parseRaw(std::string_view line) {
    // timestamp,prio,pgn,src,dst,len,b0,b1,...
    std::vector<std::string_view> fields;
    size_t start = 0;
    while (true) {
        auto comma = line.find(',', start);
        if (comma == std::string_view::npos) {
            fields.push_back(line.substr(start));
            break;
        }
        fields.push_back(line.substr(start, comma - start));
        start = comma + 1;
    }
    if (fields.size() < 6) return std::nullopt;
    double ts;
    unsigned prio, pgn, src, dst, len;
    if (!parseTimestamp(fields[0], ts) || !parseNum(fields[1], prio) || !parseNum(fields[2], pgn) ||
        !parseNum(fields[3], src) || !parseNum(fields[4], dst) || !parseNum(fields[5], len)) {
        return std::nullopt;
    }
    if (len > 8 || prio > 7 || src > 255 || dst > 255 || fields.size() < 6 + len) return std::nullopt;
    CanFrame f{makeCanId(static_cast<uint8_t>(prio), pgn, static_cast<uint8_t>(src), static_cast<uint8_t>(dst)),
               static_cast<uint8_t>(len), {}, ts};
    for (size_t i = 0; i < len; ++i) {
        if (fields[6 + i].size() != 2 || !parseNum(fields[6 + i], f.data[i], 16)) return std::nullopt;
    }
    return f;
}

}  // namespace

LogFileSource::LogFileSource(std::istream& in) : in_(in) {}

std::optional<CanFrame> LogFileSource::parseLine(std::string_view line) {
    line = trim(line);
    auto f = parseCandump(line);
    if (!f) f = parseRaw(line);
    if (f && f->timestamp > kMaxTimestamp) return std::nullopt;  // implausible: treat as unparseable
    return f;
}

std::optional<CanFrame> LogFileSource::next() {
    std::string line;
    while (std::getline(in_, line)) {
        auto t = trim(line);
        if (t.empty() || t.front() == '#') continue;
        if (auto f = parseLine(t)) return f;
        ++skipped_;
    }
    return std::nullopt;
}

}  // namespace n2k
