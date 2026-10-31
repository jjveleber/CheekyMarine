#include "VesselModel.h"

void VesselModel::setState(const VesselState &s) {
    if (!m_live) return;  // not live shows "--": never repopulate the cleared state
    m_state = s;
    emit changed();
}

void VesselModel::setLive(bool live) {
    if (m_live == live) return;
    m_live = live;
    emit liveChanged();
    if (!live) {
        m_state = VesselState{};
        emit changed();
    }
}
