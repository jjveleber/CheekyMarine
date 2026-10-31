#include "N2kParse.h"

#include <QJsonArray>
#include <QJsonValue>
#include <cmath>
#include <limits>

namespace {

using Err = std::unexpected<QString>;

Err bad(const QString &key, const char *why) { return Err(QString("%1: %2").arg(key, why)); }

// Required key holding a number or null. Returns an error string via `err` when absent or mistyped.
bool numberOrNull(const QJsonObject &o, const char *key, std::optional<double> &out, QString &err) {
    const auto it = o.find(QLatin1String(key));
    if (it == o.end()) {
        err = bad(key, "missing").error();
        return false;
    }
    if (it->isNull()) {
        out.reset();
        return true;
    }
    if (!it->isDouble()) {
        err = bad(key, "not a number").error();
        return false;
    }
    out = it->toDouble();
    return true;
}

// Optional key (absent counts as null) holding a number or null.
bool optNumber(const QJsonObject &o, const char *key, std::optional<double> &out, QString &err) {
    if (!o.contains(QLatin1String(key))) {
        out.reset();
        return true;
    }
    return numberOrNull(o, key, out, err);
}

// Converting a double outside the target type's range is undefined behaviour, so check first.
bool fitsInt(double d) { return d >= std::numeric_limits<int>::min() && d <= std::numeric_limits<int>::max(); }
bool fitsU32(double d) { return d >= 0.0 && d <= std::numeric_limits<quint32>::max(); }
// Counts and codes (sats, ship type, nav status) are never negative.
bool fitsCount(double d) { return d >= 0.0 && d <= std::numeric_limits<int>::max(); }

// Out of range reads as null.
bool optInt(const QJsonObject &o, const char *key, std::optional<int> &out, QString &err) {
    std::optional<double> d;
    if (!optNumber(o, key, d, err)) return false;
    if (d && fitsCount(*d))
        out = static_cast<int>(*d);
    else
        out.reset();
    return true;
}

bool optString(const QJsonObject &o, const char *key, QString &out, QString &err) {
    const QJsonValue v = o.value(QLatin1String(key));
    if (v.isUndefined() || v.isNull()) {
        out.clear();
        return true;
    }
    if (!v.isString()) {
        err = bad(key, "not a string").error();
        return false;
    }
    out = v.toString();
    return true;
}

}  // namespace

std::expected<int, QString> parseHello(const QJsonObject &o) {
    const QJsonValue s = o.value("schema");
    if (!s.isDouble()) return bad("schema", "missing or not a number");
    // An integer JSON number only: toInt() would truncate 1.5 to 1.
    const double d = s.toDouble();
    if (!fitsInt(d) || d != std::floor(d)) return bad("schema", "not an integer");
    return static_cast<int>(d);
}

std::expected<VesselState, QString> parseVessel(const QJsonObject &o) {
    VesselState v;
    QString err;
    std::optional<double> t, sats;
    if (!numberOrNull(o, "t", t, err) || !t) return err.isEmpty() ? bad("t", "null") : Err(err);
    v.t = *t;

    const auto pos = o.find("pos");
    if (pos == o.end()) return bad("pos", "missing");
    if (!pos->isNull()) {
        if (!pos->isObject()) return bad("pos", "not an object");
        const QJsonObject p = pos->toObject();
        if (!numberOrNull(p, "lat", v.lat, err) || !numberOrNull(p, "lon", v.lon, err)) return Err(err);
        if (!v.lat || !v.lon) v.lat = v.lon = std::nullopt;
    }

    if (!numberOrNull(o, "sog", v.sogMs, err) || !numberOrNull(o, "cog", v.cogRad, err) ||
        !numberOrNull(o, "hdg", v.hdgRad, err) || !numberOrNull(o, "variation", v.variationRad, err) ||
        !numberOrNull(o, "depth", v.depthM, err) || !numberOrNull(o, "depthOffset", v.depthOffsetM, err) ||
        !numberOrNull(o, "stw", v.stwMs, err) || !numberOrNull(o, "waterTemp", v.waterTempK, err) ||
        !numberOrNull(o, "gnssTime", v.gnssTime, err) || !numberOrNull(o, "sats", sats, err) ||
        !numberOrNull(o, "rpm", v.rpm, err))
        return Err(err);
    if (sats && fitsCount(*sats)) v.sats = static_cast<int>(*sats);

    const auto ref = o.find("hdgRef");
    if (ref == o.end()) return bad("hdgRef", "missing");
    if (!ref->isNull() && !ref->isString()) return bad("hdgRef", "not a string");
    // Anything outside the contract ("True", "Magnetic" or null) is no reference.
    if (ref->toString() == QLatin1String("True") || ref->toString() == QLatin1String("Magnetic"))
        v.hdgRef = ref->toString();
    return v;
}

std::expected<QList<AisTarget>, QString> parseAis(const QJsonObject &o) {
    const QJsonValue arr = o.value("targets");
    if (!arr.isArray()) return bad("targets", "missing or not an array");
    QList<AisTarget> out;
    QString err;
    for (const QJsonValue &tv : arr.toArray()) {
        if (!tv.isObject()) return bad("targets", "element not an object");
        const QJsonObject j = tv.toObject();
        AisTarget t;
        const QJsonValue mmsi = j.value("mmsi");
        if (!mmsi.isDouble()) return bad("mmsi", "missing or not a number");
        if (!fitsU32(mmsi.toDouble())) return bad("mmsi", "out of range");
        t.mmsi = static_cast<quint32>(mmsi.toDouble());
        if (!j.value("class").isString()) return bad("class", "missing or not a string");
        t.cls = j.value("class").toString();
        std::optional<double> age;
        if (!numberOrNull(j, "age", age, err) || !age) return err.isEmpty() ? bad("age", "null") : Err(err);
        t.age = *age;
        if (!optNumber(j, "lat", t.lat, err) || !optNumber(j, "lon", t.lon, err) ||
            !optNumber(j, "sog", t.sogMs, err) || !optNumber(j, "cog", t.cogRad, err) ||
            !optNumber(j, "hdg", t.hdgRad, err) || !optNumber(j, "posAge", t.posAge, err) ||
            !optInt(j, "shipType", t.shipType, err) || !optInt(j, "navStatus", t.navStatus, err) ||
            !optString(j, "name", t.name, err))
            return Err(err);
        if (!t.lat || !t.lon) t.lat = t.lon = std::nullopt;
        out.append(t);
    }
    return out;
}
