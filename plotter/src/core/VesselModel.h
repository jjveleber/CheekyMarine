#pragma once
#include <QObject>

#include "VesselState.h"

class VesselModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool live READ live NOTIFY liveChanged)
public:
    explicit VesselModel(QObject *parent = nullptr) : QObject(parent) {}
    bool live() const { return m_live; }
    const VesselState &state() const { return m_state; }

public slots:
    void setState(const VesselState &s);
    void setLive(bool live);

signals:
    void liveChanged();
    void changed();

private:
    VesselState m_state;
    bool m_live = false;
};
