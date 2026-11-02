#pragma once
#include <QAbstractListModel>
#include <QList>

#include "VesselState.h"

class AisModel : public QAbstractListModel {
    Q_OBJECT
public:
    enum Role { MmsiRole = Qt::UserRole + 1, ClsRole, LatRole, LonRole, SogMsRole, CogRadRole, HdgRadRole, NameRole, PosAgeRole, AgeRole };
    explicit AisModel(QObject *parent = nullptr) : QAbstractListModel(parent) {}
    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    QList<AisTarget> targets() const { return m_targets; }

public slots:
    void setTargets(const QList<AisTarget> &t);
    void setLive(bool live);

private:
    QList<AisTarget> m_targets;
    bool m_live = false;
};
