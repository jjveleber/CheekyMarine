#include "ViewDraft.h"
#include "Settings.h"
#include "Tilings.h"
#include "VesselModel.h"
#include <QDebug>
#include <QJsonObject>
#include <algorithm>
#include <cmath>

namespace {
// Emits dataChanged for the formatted and unit roles of every row on vessel and unit setting changes.
void refreshValuesOn(QAbstractListModel* m, VesselModel& vessel, Settings& settings, QList<int> roles) {
    const auto refresh = [m, roles] {
        if (m->rowCount() > 0) emit m->dataChanged(m->index(0), m->index(m->rowCount() - 1), roles);
    };
    QObject::connect(&vessel, &VesselModel::changed, m, refresh);
    onUnitSettingsChanged(settings, m, refresh);
}

// Same row count: dataChanged; otherwise a reset.
template <typename T>
void replaceRows(QAbstractListModel* m, QList<T>& rows, const QList<T>& next, auto begin, auto end) {
    if (next == rows) return;
    if (next.size() == rows.size()) {
        rows = next;
        emit m->dataChanged(m->index(0), m->index(int(rows.size()) - 1));
        return;
    }
    begin();
    rows = next;
    end();
}
} // namespace

DraftSlotsModel::DraftSlotsModel(VesselModel& vessel, Settings& settings, QObject* parent)
    : QAbstractListModel(parent), m_vessel(vessel), m_settings(settings) {
    refreshValuesOn(this, m_vessel, m_settings, {FormattedRole, UnitRole});
}

int DraftSlotsModel::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : int(m_slots.size()); }

QVariant DraftSlotsModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() >= m_slots.size()) return {};
    const ViewSlot& s = m_slots.at(index.row());
    switch (role) {
    case SlotIdRole: return slotIdName(s.id);
    case OnRole: return s.on;
    case FieldRole: return fieldName(s.field);
    case FieldLabelRole: return fieldLabel(s.field);
    case SizeMmRole: return s.sizeMm;
    case WidestSampleRole: return widestSample(s.field);
    case FormattedRole:
    case UnitRole: return fieldRoleText(s.field, role == UnitRole ? FieldText::Unit : FieldText::Value, m_vessel, m_settings);
    }
    return {};
}

QHash<int, QByteArray> DraftSlotsModel::roleNames() const {
    return {{SlotIdRole, "slotId"},   {OnRole, "on"},           {FieldRole, "field"}, {FieldLabelRole, "fieldLabel"},
            {SizeMmRole, "sizeMm"}, {FormattedRole, "formatted"}, {UnitRole, "unit"}, {WidestSampleRole, "widestSample"}};
}

void DraftSlotsModel::setSlotList(const QList<ViewSlot>& slotList) {
    replaceRows(this, m_slots, slotList, [this] { beginResetModel(); }, [this] { endResetModel(); });
}

DraftCellsModel::DraftCellsModel(VesselModel& vessel, Settings& settings, QObject* parent)
    : QAbstractListModel(parent), m_vessel(vessel), m_settings(settings) {
    refreshValuesOn(this, m_vessel, m_settings, {FormattedRole, UnitRole});
}

int DraftCellsModel::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : int(m_fields.size()); }

QVariant DraftCellsModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() >= m_fields.size()) return {};
    const Field f = m_fields.at(index.row());
    switch (role) {
    case FieldRole: return fieldName(f);
    case FieldLabelRole: return fieldLabel(f);
    case FormattedRole:
    case UnitRole: return fieldRoleText(f, role == UnitRole ? FieldText::Unit : FieldText::Value, m_vessel, m_settings);
    }
    return {};
}

QHash<int, QByteArray> DraftCellsModel::roleNames() const {
    return {{FieldRole, "field"}, {FieldLabelRole, "fieldLabel"}, {FormattedRole, "formatted"}, {UnitRole, "unit"}};
}

void DraftCellsModel::setFields(const QList<Field>& fields) {
    replaceRows(this, m_fields, fields, [this] { beginResetModel(); }, [this] { endResetModel(); });
}

ViewDraft::ViewDraft(VesselModel& vessel, Settings& settings, QObject* parent)
    : QObject(parent), m_slotsModel(new DraftSlotsModel(vessel, settings, this)),
      m_cellsModel(new DraftCellsModel(vessel, settings, this)) {
    load(viewFromJson({}));
}

void ViewDraft::setId(const QString& id) {
    if (id == m_view.id) return;
    m_view.id = id;
    emit idChanged();
    setDirty(true);
}

void ViewDraft::setName(const QString& name) {
    const QString v = name.left(kMaxNameChars);
    if (v == m_view.name) return;
    m_view.name = v;
    emit nameChanged();
    setDirty(true);
}

void ViewDraft::setShortName(const QString& shortName) {
    const QString v = shortName.left(kMaxShortChars);
    if (v == m_view.shortName) return;
    m_view.shortName = v;
    emit shortNameChanged();
    setDirty(true);
}

void ViewDraft::setIcon(const QString& icon) {
    if (icon == m_view.icon) return;
    m_view.icon = icon;
    emit iconChanged();
    setDirty(true);
}

void ViewDraft::setChart(const QString& chart) {
    const auto c = viewChartFromName(chart);
    if (!c) {
        qWarning() << "view draft: unknown chart" << chart;
        return;
    }
    if (*c == m_view.chart) return;
    m_view.chart = *c;
    emit chartChanged();
    setDirty(true);
}

void ViewDraft::setLayout(const QString& key) {
    const auto l = layoutFromKey(key);
    if (!l) {
        qWarning() << "view draft: not a layout" << key;
        return;
    }
    const QString canonical = canonicalKey(*l);
    if (canonical == m_view.cells.layout) return;
    QList<Field> fields = m_view.cells.fields.mid(0, l->cells.size());
    while (fields.size() < l->cells.size()) fields << defaultCellField(int(fields.size()));
    m_view.cells = {canonical, fields};
    m_cellsModel->setFields(fields);
    emit layoutChanged();
    setDirty(true);
}

void ViewDraft::setFavorite(bool on) {
    if (on == m_view.favorite) return;
    m_view.favorite = on;
    emit favoriteChanged();
    setDirty(true);
}

void ViewDraft::load(const View& view) {
    m_view = view;
    QList<ViewSlot>& slotList = m_view.slotList;
    bool whole = slotList.size() == 8;
    for (int i = 0; whole && i < 8; ++i) whole = int(slotList[i].id) == i;
    if (!whole) {
        // setSlot indexes by SlotId: rebuild in SlotId order, the first entry of an id winning.
        qWarning() << "view draft: slot list of" << view.id << "is not the eight slots in order; made whole";
        QList<ViewSlot> fixed = defaultViewSlots();
        QList<bool> seen(fixed.size(), false);
        for (const ViewSlot& s : view.slotList) {
            if (int(s.id) < 0 || int(s.id) >= fixed.size() || seen[int(s.id)]) continue;
            seen[int(s.id)] = true;
            fixed[int(s.id)] = s;
        }
        slotList = fixed;
    }
    m_slotsModel->setSlotList(m_view.slotList);
    m_cellsModel->setFields(m_view.cells.fields);
    for (auto sig : {&ViewDraft::idChanged, &ViewDraft::nameChanged, &ViewDraft::shortNameChanged, &ViewDraft::iconChanged,
                     &ViewDraft::chartChanged, &ViewDraft::layoutChanged, &ViewDraft::favoriteChanged})
        emit(this->*sig)();
    setDirty(false);
}

View ViewDraft::toView() const {
    View v = m_view;
    if (v.shortName.isEmpty()) v.shortName = shortFromName(v.name);
    return v;
}

void ViewDraft::loadJson(const QVariantMap& json) { load(viewFromJson(QJsonObject::fromVariantMap(json))); }

QVariantMap ViewDraft::toJson() const { return viewToJson(toView()).toVariantMap(); }

void ViewDraft::setSlot(const QString& slotId, bool on, const QString& field, double sizeMm) {
    const auto id = slotIdFromName(slotId);
    const auto f = fieldFromName(field);
    if (!id || !f) {
        qWarning() << "view draft: rejected slot" << slotId << field;
        return;
    }
    ViewSlot& cur = m_view.slotList[int(*id)];
    const ViewSlot s{*id, on, *f, std::max(kMinSizeMm, std::round(sizeMm * 10.0) / 10.0), cur.extra};
    if (s == cur) return;
    cur = s;
    m_slotsModel->setSlotList(m_view.slotList);
    setDirty(true);
}

void ViewDraft::setCellField(int index, const QString& field) {
    const auto f = fieldFromName(field);
    if (index < 0 || index >= m_view.cells.fields.size() || !f) {
        qWarning() << "view draft: rejected cell" << index << field;
        return;
    }
    if (m_view.cells.fields[index] == *f) return;
    m_view.cells.fields[index] = *f;
    m_cellsModel->setFields(m_view.cells.fields);
    setDirty(true);
}

void ViewDraft::setDirty(bool dirty) {
    if (dirty == m_dirty) return;
    m_dirty = dirty;
    emit dirtyChanged();
}
