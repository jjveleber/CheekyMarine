#pragma once
#include <QJsonObject>
#include <QList>
#include <QString>
#include <expected>

#include "VesselState.h"

std::expected<int, QString> parseHello(const QJsonObject &o);
std::expected<VesselState, QString> parseVessel(const QJsonObject &o);
std::expected<QList<AisTarget>, QString> parseAis(const QJsonObject &o);
