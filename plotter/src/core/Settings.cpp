#include "Settings.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QSqlError>
#include <QSqlQuery>
#include <cmath>
#include <functional>
#include <map>

namespace {

using Check = std::function<bool(const QJsonValue&)>;

Check oneOf(std::initializer_list<const char*> allowed) {
    QStringList l;
    for (const char* a : allowed)
        l << QString::fromLatin1(a);
    return [l](const QJsonValue& v) { return v.isString() && l.contains(v.toString()); };
}
Check isBool() { return [](const QJsonValue& v) { return v.isBool(); }; }
Check isNum(double min, double max = 1e12) {
    return [=](const QJsonValue& v) { return v.isDouble() && v.toDouble() >= min && v.toDouble() <= max; };
}
Check isInt(int min) {
    return [=](const QJsonValue& v) { return v.isDouble() && v.toDouble() == std::floor(v.toDouble()) && v.toInt() >= min; };
}

struct Def {
    QJsonValue def;
    Check ok;
};

const std::map<QString, Def>& defs() {
    static const std::map<QString, Def> d{
        {"depthUnit", {"ft", oneOf({"ft", "m", "fm"})}},
        {"speedUnit", {"kn", oneOf({"kn", "mph", "kmh"})}},
        {"tempUnit", {"F", oneOf({"F", "C"})}},
        {"applyDepthOffset", {true, isBool()}},
        {"shallowM", {1.8288, isNum(Settings::kMinDepthM, Settings::kMaxDepthM)}},
        {"safetyM", {3.048, isNum(Settings::kMinDepthM, Settings::kMaxDepthM)}},
        {"deepM", {9.144, isNum(Settings::kMinDepthM, Settings::kMaxDepthM)}},
        {"orientation", {"head", oneOf({"north", "head", "course"})}},
        {"paletteMode", {"auto", oneOf({"auto", "day", "dusk", "night"})}},
        {"chartMode", {"nav", [](const QJsonValue& v) { return v.isString() && !v.toString().isEmpty(); }}},
        {"touchLockTimeoutS", {120, isInt(0)}},
        {"panelDiagonalIn", {10.1, isNum(1, 100)}},
        {"trackRecording", {false, isBool()}},
        {"trackIntervalS", {5, isInt(1)}},
        {"trackMinDistanceM", {10, isNum(0)}},
        {"slots", {QJsonArray(), [](const QJsonValue&) { return true; }}}, // owned by the slot editor (Task 12)
        {"bigNumbers", {QJsonArray{"depth", "sog"}, [](const QJsonValue& v) {
                            if (!v.isArray())
                                return false;
                            for (const auto& e : v.toArray())
                                if (!e.isString())
                                    return false;
                            return true;
                        }}},
    };
    return d;
}

// Scalars are not valid top-level JSON documents for QJsonDocument, so wrap them in an array.
QString toText(const QJsonValue& v) {
    const QByteArray a = QJsonDocument(QJsonArray{v}).toJson(QJsonDocument::Compact);
    return QString::fromUtf8(a.mid(1, a.size() - 2));
}
std::optional<QJsonValue> fromText(const QString& s) {
    QJsonParseError e;
    const auto doc = QJsonDocument::fromJson(("[" + s + "]").toUtf8(), &e);
    if (e.error != QJsonParseError::NoError || doc.array().size() != 1)
        return std::nullopt;
    return doc.array().at(0);
}

bool depthsValid(double a, double b, double c) {
    return Settings::depthsProblem(a, b, c).isEmpty();
}

} // namespace

Settings::Settings(Store& store, QObject* parent) : QObject(parent), m_store(store) {
    for (const auto& [k, d] : defs())
        m_v.insert(k, d.def);
    QSqlQuery q(m_store.db());
    if (!q.exec(QStringLiteral("SELECT key, value FROM settings"))) {
        qWarning() << "settings: read failed, using defaults:" << q.lastError().text();
        return;
    }
    while (q.next()) {
        const QString key = q.value(0).toString();
        const auto it = defs().find(key);
        if (it == defs().end())
            continue; // unknown (newer app): left alone
        const auto v = fromText(q.value(1).toString());
        if (!v || !it->second.ok(*v)) {
            qWarning() << "settings: unusable value for" << key << "- using default";
            continue;
        }
        m_v.insert(key, *v);
    }
    if (!depthsValid(shallowM(), safetyM(), deepM())) {
        qWarning() << "settings: stored depth thresholds are inconsistent (shallowM/safetyM/deepM) - using defaults";
        for (const char* k : {"shallowM", "safetyM", "deepM"})
            m_v.insert(k, defs().at(k).def);
    }
}

QStringList Settings::bigNumbers() const {
    QStringList l;
    for (const auto& e : m_v.value("bigNumbers").toArray())
        l << e.toString();
    return l;
}

void Settings::setBigNumbers(const QStringList& v) {
    if (put("bigNumbers", QJsonArray::fromStringList(v)))
        emit bigNumbersChanged();
}

bool Settings::write(const QString& key, const QJsonValue& v) {
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("INSERT INTO settings(key, value) VALUES(?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value"));
    q.addBindValue(key);
    q.addBindValue(toText(v));
    if (q.exec())
        return true;
    qWarning() << "settings: write failed for" << key << q.lastError().text();
    return false;
}

bool Settings::put(const QString& key, const QJsonValue& v) {
    const auto it = defs().find(key);
    if (it == defs().end() || !it->second.ok(v)) {
        qWarning() << "settings: rejected value for" << key;
        return false;
    }
    if (m_v.value(key) == v)
        return false;
    if (!write(key, v))
        return false;
    m_v.insert(key, v);
    return true;
}

QString Settings::depthsProblem(double a, double b, double c) {
    if (a < kMinDepthM)
        return QStringLiteral("Depths must be at least %1 m.").arg(kMinDepthM);
    if (c > kMaxDepthM)
        return QStringLiteral("Depths must be at most %1 m.").arg(kMaxDepthM);
    if (!(a < b))
        return QStringLiteral("Shallow must be less than safety.");
    if (!(b < c))
        return QStringLiteral("Safety must be less than deep.");
    return QString();
}

bool Settings::setDepths(double shallow, double safety, double deep) {
    if (!depthsValid(shallow, safety, deep))
        return false;
    const double nv[3] = {shallow, safety, deep};
    const char* keys[3] = {"shallowM", "safetyM", "deepM"};
    const double old[3] = {shallowM(), safetyM(), deepM()};
    QSqlDatabase db = m_store.db();
    if (!db.transaction())
        return false;
    for (int i = 0; i < 3; ++i) {
        if (nv[i] != old[i] && !write(keys[i], nv[i])) {
            db.rollback();
            return false;
        }
    }
    if (!db.commit()) {
        db.rollback();
        return false;
    }
    for (int i = 0; i < 3; ++i)
        m_v.insert(keys[i], nv[i]);
    if (nv[0] != old[0]) emit shallowMChanged();
    if (nv[1] != old[1]) emit safetyMChanged();
    if (nv[2] != old[2]) emit deepMChanged();
    return true;
}

UnitPrefs Settings::unitPrefs() const {
    UnitPrefs p;
    const QString d = depthUnit(), s = speedUnit(), t = tempUnit();
    p.depth = d == "m" ? DepthUnit::Metres : d == "fm" ? DepthUnit::Fathoms : DepthUnit::Feet;
    p.speed = s == "mph" ? SpeedUnit::Mph : s == "kmh" ? SpeedUnit::Kmh : SpeedUnit::Knots;
    p.temp = t == "C" ? TempUnit::C : TempUnit::F;
    p.applyDepthOffset = applyDepthOffset();
    return p;
}
