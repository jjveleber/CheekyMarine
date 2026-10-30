#include "Slots.h"
#include "Settings.h"
#include "VesselModel.h"
#include <QDebug>
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

QJsonArray slotsToJson(const QList<SlotConfig>& configs) {
    QJsonArray a;
    for (const SlotConfig& s : configs)
        a.append(QJsonObject{{"id", slotIdName(s.id)},
                             {"on", s.on},
                             {"field", fieldName(s.field)},
                             {"size", slotSizeName(s.size)}});
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

QVariantList fieldChoices() {
    QVariantList l;
    for (Field f : kFields)
        l.append(QVariantMap{{"name", fieldName(f)}, {"label", fieldLabel(f)}});
    return l;
}

SlotsModel::SlotsModel(Settings& settings, VesselModel& vessel, QObject* parent)
    : QAbstractListModel(parent), m_settings(settings), m_vessel(vessel) {
    m_slots = slotsFromJson(m_settings.slotsJson().toArray());
    connect(&m_settings, &Settings::slotsJsonChanged, this, &SlotsModel::reload);
    connect(&m_vessel, &VesselModel::changed, this, &SlotsModel::refreshValues);
    for (auto sig : {&Settings::depthUnitChanged, &Settings::speedUnitChanged, &Settings::tempUnitChanged,
                     &Settings::applyDepthOffsetChanged})
        connect(&m_settings, sig, this, &SlotsModel::refreshValues);
}

int SlotsModel::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : int(m_slots.size()); }

QVariant SlotsModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() >= m_slots.size()) return {};
    const SlotConfig& s = m_slots.at(index.row());
    switch (role) {
    case SlotIdRole: return slotIdName(s.id);
    case OnRole: return s.on;
    case FieldRole: return fieldName(s.field);
    case FieldLabelRole: return fieldLabel(s.field);
    case SizeRole: return slotSizeName(s.size);
    case FormattedRole: return formatValue(s.field, m_vessel.state(), m_settings.unitPrefs());
    case UnitRole: return unitLabel(s.field, m_vessel.state(), m_settings.unitPrefs());
    }
    return {};
}

QHash<int, QByteArray> SlotsModel::roleNames() const {
    return {{SlotIdRole, "slotId"}, {OnRole, "on"},           {FieldRole, "field"}, {FieldLabelRole, "fieldLabel"},
            {SizeRole, "size"},     {FormattedRole, "formatted"}, {UnitRole, "unit"}};
}

void SlotsModel::setSlot(const QString& id, bool on, const QString& field, const QString& size) {
    const auto i = slotIdFromName(id);
    const auto f = fieldFromName(field);
    const auto z = slotSizeFromName(size);
    if (!i || !f || !z) {
        qWarning() << "slots: rejected" << id << field << size;
        return;
    }
    QList<SlotConfig> next = m_slots;
    next[int(*i)] = {*i, on, *f, *z};
    setSlotConfigs(next);
}

void SlotsModel::setSlotConfigs(const QList<SlotConfig>& configs) {
    // Settings emits slotsJsonChanged, and reload() takes the stored value back.
    m_settings.setSlotsJson(slotsToJson(configs));
}

void SlotsModel::reload() {
    const QList<SlotConfig> next = slotsFromJson(m_settings.slotsJson().toArray());
    if (next == m_slots) return;
    m_slots = next;
    emit dataChanged(index(0), index(int(m_slots.size()) - 1));
}

void SlotsModel::refreshValues() {
    emit dataChanged(index(0), index(int(m_slots.size()) - 1), {FormattedRole, UnitRole});
}
