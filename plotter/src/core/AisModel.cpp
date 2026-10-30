#include "AisModel.h"

int AisModel::rowCount(const QModelIndex &parent) const { return parent.isValid() ? 0 : static_cast<int>(m_targets.size()); }

static QVariant opt(const std::optional<double> &v) { return v ? QVariant(*v) : QVariant(); }

QVariant AisModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= m_targets.size()) return {};
    const AisTarget &t = m_targets.at(index.row());
    switch (role) {
    case MmsiRole: return t.mmsi;
    case ClsRole: return t.cls;
    case LatRole: return opt(t.lat);
    case LonRole: return opt(t.lon);
    case SogMsRole: return opt(t.sogMs);
    case CogRadRole: return opt(t.cogRad);
    case HdgRadRole: return opt(t.hdgRad);
    case NameRole: return t.name;
    case PosAgeRole: return opt(t.posAge);
    case AgeRole: return t.age;
    }
    return {};
}

QHash<int, QByteArray> AisModel::roleNames() const {
    return {{MmsiRole, "mmsi"},     {ClsRole, "cls"},       {LatRole, "lat"},   {LonRole, "lon"},
            {SogMsRole, "sogMs"},   {CogRadRole, "cogRad"}, {HdgRadRole, "hdgRad"}, {NameRole, "name"},
            {PosAgeRole, "posAge"}, {AgeRole, "age"}};
}

void AisModel::setTargets(const QList<AisTarget> &t) {
    beginResetModel();
    m_targets = t;
    endResetModel();
}

void AisModel::setLive(bool live) {
    if (m_live == live) return;
    m_live = live;
    if (!live && !m_targets.isEmpty()) setTargets({});
}
