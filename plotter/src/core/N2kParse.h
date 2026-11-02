#pragma once
#include <QJsonObject>
#include <QList>
#include <QString>
#include <expected>

#include "VesselState.h"

// The daemon-to-plotter JSON (see README.md "JSON messages"). This is our contract, not an NMEA 2000
// rule. A vessel message must carry every key (null when there is no data); a missing key is an
// error. An AIS target must carry mmsi, class and age; every other target key is optional and an
// absent key reads as null, so a daemon may omit a target key it has no value for.
std::expected<int, QString> parseHello(const QJsonObject &o);
std::expected<VesselState, QString> parseVessel(const QJsonObject &o);
std::expected<QList<AisTarget>, QString> parseAis(const QJsonObject &o);
