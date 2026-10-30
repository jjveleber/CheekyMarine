#pragma once
#include <QString>
#include <QtGlobal>
#include <optional>

struct VesselState {
    double t = 0;
    std::optional<double> lat, lon, sogMs, cogRad, hdgRad, variationRad, depthM, depthOffsetM, stwMs,
        waterTempK, gnssTime, rpm;
    std::optional<int> sats;
    QString hdgRef;
};

struct AisTarget {
    quint32 mmsi = 0;
    QString cls;
    std::optional<double> lat, lon, sogMs, cogRad, hdgRad, posAge;
    double age = 0;
    QString name;
    std::optional<int> shipType, navStatus;
};
