#include "NumbersModel.h"
#include "Settings.h"
#include "Slots.h"
#include "VesselModel.h"
#include <QDebug>

namespace {
const Field kDefaults[NumbersModel::kMaxCells] = {Field::Depth, Field::Sog, Field::Cog, Field::Stw};
} // namespace

NumbersModel::NumbersModel(Settings& settings, VesselModel& vessel, QObject* parent)
    : QAbstractListModel(parent), m_settings(settings), m_vessel(vessel) {
    reload();
    connect(&m_settings, &Settings::bigNumbersChanged, this, &NumbersModel::reload);
    connect(&m_vessel, &VesselModel::changed, this, &NumbersModel::refreshValues);
    for (auto sig : {&Settings::depthUnitChanged, &Settings::speedUnitChanged, &Settings::tempUnitChanged,
                     &Settings::applyDepthOffsetChanged})
        connect(&m_settings, sig, this, &NumbersModel::refreshValues);
}

int NumbersModel::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : count(); }

QVariant NumbersModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() >= m_fields.size()) return {};
    const Field f = m_fields.at(index.row());
    switch (role) {
    case FieldRole: return fieldName(f);
    case FieldLabelRole: return fieldLabel(f);
    case FormattedRole: return formatValue(f, m_vessel.state(), m_settings.unitPrefs());
    case UnitRole: return unitLabel(f, m_vessel.state(), m_settings.unitPrefs());
    }
    return {};
}

QHash<int, QByteArray> NumbersModel::roleNames() const {
    return {{FieldRole, "field"}, {FieldLabelRole, "fieldLabel"}, {FormattedRole, "formatted"}, {UnitRole, "unit"}};
}

QVariantList NumbersModel::fieldChoicesList() const { return fieldChoices(); }

void NumbersModel::setField(int index, const QString& name) {
    const auto f = fieldFromName(name);
    if (index < 0 || index >= count() || !f) {
        qWarning() << "numbers: rejected field" << index << name;
        return;
    }
    QList<Field> next = m_fields;
    next[index] = *f;
    QStringList names;
    for (Field x : next) names << fieldName(x);
    m_settings.setBigNumbers(names); // reload() follows from bigNumbersChanged
}

void NumbersModel::setCount(int n) {
    if (n < kMinCells || n > kMaxCells) {
        qWarning() << "numbers: rejected count" << n;
        return;
    }
    QStringList names;
    for (int i = 0; i < n; ++i) names << fieldName(i < count() ? m_fields.at(i) : kDefaults[i]);
    m_settings.setBigNumbers(names);
}

void NumbersModel::reload() {
    const QStringList stored = m_settings.bigNumbers();
    QList<Field> next;
    for (int i = 0; i < kMaxCells && (i < stored.size() || i < kMinCells); ++i) {
        const auto f = i < stored.size() ? fieldFromName(stored.at(i)) : std::nullopt;
        next << f.value_or(kDefaults[i]);
    }
    if (next == m_fields) return;
    const bool countChanges = next.size() != m_fields.size();
    beginResetModel();
    m_fields = next;
    endResetModel();
    if (countChanges) emit countChanged();
}

void NumbersModel::refreshValues() {
    if (m_fields.isEmpty()) return;
    emit dataChanged(index(0), index(count() - 1), {FormattedRole, UnitRole});
}
