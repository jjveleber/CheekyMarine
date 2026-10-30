#include "core/DepthFilters.h"
#include <QJsonArray>
#include <cmath>

namespace {

constexpr double kEps = 1e-6;

bool near(double a, double b) { return std::fabs(a - b) < kEps; }

bool isDepthField(const QString& n) {
    return n == QLatin1String("DRVAL1") || n == QLatin1String("VALDCO") || n == QLatin1String("depth") ||
           n == QLatin1String("VALSOU");
}

// True when a ["get", NAME] with a depth field NAME appears anywhere inside `v`.
bool readsDepth(const QJsonValue& v) {
    if (!v.isArray()) return false;
    const QJsonArray a = v.toArray();
    if (a.size() == 2 && a[0].isString() && a[0].toString() == QLatin1String("get") && a[1].isString() &&
        isDepthField(a[1].toString()))
        return true;
    if (!a.isEmpty() && a[0].isString() && a[0].toString() == QLatin1String("literal")) return false;
    for (const auto& e : a)
        if (readsDepth(e)) return true;
    return false;
}

bool isComparison(const QString& op) {
    return op == QLatin1String("<") || op == QLatin1String("<=") || op == QLatin1String(">") ||
           op == QLatin1String(">=") || op == QLatin1String("==");
}

struct Mapper {
    QString layer;
    double fromShallow = 0, fromSafety = 0, fromDeep = 0, fromContour = 0;
    Depths to{};
    double toContour = 0;
    QString error;

    // Maps one depth literal, or records the error and returns it unchanged.
    QJsonValue mapLiteral(double v) {
        if (layer == QLatin1String("depcnt-safety") && near(v, fromContour)) return toContour;
        if (near(v, fromShallow)) return to.shallowM;
        if (near(v, fromSafety)) return to.safetyM;
        if (near(v, fromDeep)) return to.deepM;
        if (error.isEmpty())
            error = QStringLiteral("layer %1: unmapped depth literal %2").arg(layer).arg(v, 0, 'g', 10);
        return v;
    }

    QJsonValue walk(const QJsonValue& v) {
        if (!v.isArray()) return v;
        QJsonArray a = v.toArray();
        if (a.isEmpty()) return v;
        if (a[0].isString() && a[0].toString() == QLatin1String("literal")) return v; // data, not a depth test
        const bool cmp = a.size() == 3 && a[0].isString() && isComparison(a[0].toString());
        for (int i = 1; i < a.size(); ++i) {
            if (cmp && a[i].isDouble() && readsDepth(a[i == 1 ? 2 : 1])) a[i] = mapLiteral(a[i].toDouble());
            else a[i] = walk(a[i]);
        }
        return a;
    }
};

} // namespace

double safetyContour(const QList<double>& valdco, double safetyM) {
    for (double v : valdco)
        if (v >= safetyM) return v;
    return safetyM;
}

std::expected<QHash<QString, QJsonValue>, QString> depthFilters(const QJsonObject& style, const Depths& target,
                                                                double safetyContourM) {
    const QJsonObject cm =
        style.value(QStringLiteral("metadata")).toObject().value(QStringLiteral("cheekymarine")).toObject();
    const QJsonObject depths = cm.value(QStringLiteral("depths")).toObject();
    if (!depths.value(QStringLiteral("shallow_m")).isDouble() || !depths.value(QStringLiteral("safety_m")).isDouble() ||
        !depths.value(QStringLiteral("deep_m")).isDouble() || !depths.value(QStringLiteral("layers")).isArray())
        return std::unexpected(QStringLiteral("style has no metadata.cheekymarine.depths"));

    Mapper m;
    m.fromShallow = depths.value(QStringLiteral("shallow_m")).toDouble();
    m.fromSafety = depths.value(QStringLiteral("safety_m")).toDouble();
    m.fromDeep = depths.value(QStringLiteral("deep_m")).toDouble();
    m.fromContour = cm.value(QStringLiteral("safety_contour_m")).toDouble(-1e9);
    m.to = target;
    m.toContour = safetyContourM;

    QHash<QString, QJsonObject> byId;
    for (const auto& l : style.value(QStringLiteral("layers")).toArray()) {
        const QJsonObject o = l.toObject();
        byId.insert(o.value(QStringLiteral("id")).toString(), o);
    }

    QHash<QString, QJsonValue> out;
    for (const auto& idv : depths.value(QStringLiteral("layers")).toArray()) {
        const QString id = idv.toString();
        auto it = byId.constFind(id);
        if (it == byId.constEnd()) continue;
        m.layer = id;
        m.error.clear();
        const QJsonValue mapped = m.walk(it->value(QStringLiteral("filter")));
        if (!m.error.isEmpty()) return std::unexpected(m.error);
        out.insert(id, mapped);
    }
    return out;
}
