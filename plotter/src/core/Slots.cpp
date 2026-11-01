#include "Slots.h"
#include "Settings.h"
#include "VesselModel.h"
#include <QJsonObject>
#include <array>

namespace {
struct IdName {
    SlotId id;
    const char16_t* name;
};
constexpr IdName kIds[] = {
    {SlotId::TL, u"TL"},   {SlotId::TR, u"TR"},         {SlotId::BL, u"BL"},     {SlotId::BR, u"BR"},
    {SlotId::Top, u"Top"}, {SlotId::Bottom, u"Bottom"}, {SlotId::Left, u"Left"}, {SlotId::Right, u"Right"},
};
struct SizeName {
    SlotSize size;
    const char16_t* name;
};
constexpr SizeName kSizes[] = {{SlotSize::Small, u"small"}, {SlotSize::Medium, u"medium"}, {SlotSize::Large, u"large"}};

constexpr std::array<Field, 9> kFields{Field::Depth,     Field::Sog,      Field::Stw,  Field::Cog, Field::Heading,
                                       Field::WaterTemp, Field::Position, Field::Time, Field::Rpm};
} // namespace

QList<SlotConfig> defaultSlots() {
    return {
        {SlotId::TL, true, Field::Depth, SlotSize::Large},
        {SlotId::TR, true, Field::Sog, SlotSize::Large},
        {SlotId::BL, false, Field::Cog, SlotSize::Medium},
        {SlotId::BR, false, Field::WaterTemp, SlotSize::Medium},
        {SlotId::Top, false, Field::Time, SlotSize::Small},
        {SlotId::Bottom, false, Field::Position, SlotSize::Small},
        {SlotId::Left, false, Field::Stw, SlotSize::Medium},
        {SlotId::Right, false, Field::Heading, SlotSize::Medium},
    };
}

QJsonArray slotsToJson(const QList<SlotConfig>& configs, const QJsonArray& stored) {
    QJsonArray a = stored;
    for (const SlotConfig& s : configs) {
        const QString id = slotIdName(s.id);
        int k = 0;
        while (k < a.size() && a[k].toObject().value("id").toString() != id) ++k; // first entry wins
        QJsonObject o = k < a.size() ? a[k].toObject() : QJsonObject{{"id", id}};
        o["on"] = s.on;
        o["field"] = fieldName(s.field);
        o["size"] = slotSizeName(s.size);
        if (k < a.size()) a[k] = o;
        else a.append(o);
    }
    return a;
}

QList<SlotConfig> slotsFromJson(const QJsonArray& json) {
    QList<SlotConfig> out = defaultSlots();
    QList<bool> seen(out.size(), false);
    for (const QJsonValue& v : json) {
        if (!v.isObject()) continue;
        const QJsonObject o = v.toObject();
        const auto id = slotIdFromName(o.value("id").toString());
        if (!id) continue;
        const int i = int(*id);
        if (seen[i]) continue;
        seen[i] = true;
        SlotConfig& s = out[i];
        if (o.value("on").isBool()) s.on = o.value("on").toBool();
        if (const auto f = fieldFromName(o.value("field").toString())) s.field = *f;
        if (const auto z = slotSizeFromName(o.value("size").toString())) s.size = *z;
    }
    return out;
}

QString slotIdName(SlotId id) {
    for (const auto& e : kIds)
        if (e.id == id) return QString::fromUtf16(e.name);
    return {};
}

std::optional<SlotId> slotIdFromName(QStringView name) {
    for (const auto& e : kIds)
        if (name == QStringView(e.name)) return e.id;
    return std::nullopt;
}

QString slotSizeName(SlotSize size) {
    for (const auto& e : kSizes)
        if (e.size == size) return QString::fromUtf16(e.name);
    return {};
}

std::optional<SlotSize> slotSizeFromName(QStringView name) {
    for (const auto& e : kSizes)
        if (name == QStringView(e.name)) return e.size;
    return std::nullopt;
}

QString fieldLabel(Field field) {
    switch (field) {
    case Field::Depth: return QStringLiteral("Depth");
    case Field::Sog: return QStringLiteral("SOG");
    case Field::Stw: return QStringLiteral("STW");
    case Field::Cog: return QStringLiteral("COG");
    case Field::Heading: return QStringLiteral("HDG");
    case Field::WaterTemp: return QStringLiteral("Water temp");
    case Field::Position: return QStringLiteral("Position");
    case Field::Time: return QStringLiteral("Time");
    case Field::Rpm: return QStringLiteral("RPM");
    }
    return {};
}

QString widestSample(Field field) {
    switch (field) {
    case Field::Depth: return QStringLiteral("9999.9");
    case Field::Sog:
    case Field::Stw: return QStringLiteral("99.9");
    case Field::Cog:
    case Field::Heading: return QStringLiteral("359");
    case Field::WaterTemp: return QStringLiteral("999.9");
    case Field::Position: return QStringLiteral("89°59.999'N\n122°59.999'W");
    case Field::Time: return QStringLiteral("88:88:88");
    case Field::Rpm: return QStringLiteral("9999");
    }
    return {};
}

QVariantList fieldChoices() {
    QVariantList l;
    for (Field f : kFields)
        l.append(QVariantMap{{"name", fieldName(f)}, {"label", fieldLabel(f)}});
    return l;
}

QString fieldRoleText(Field field, bool unit, const VesselModel& vessel, const Settings& settings) {
    return unit ? unitLabel(field, vessel.state(), settings.unitPrefs())
                : formatValue(field, vessel.state(), settings.unitPrefs());
}

void onUnitSettingsChanged(Settings& settings, QObject* context, const std::function<void()>& refresh) {
    for (auto sig : {&Settings::depthUnitChanged, &Settings::speedUnitChanged, &Settings::tempUnitChanged,
                     &Settings::applyDepthOffsetChanged})
        QObject::connect(&settings, sig, context, refresh);
}
