#pragma once
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QList>
#include <QString>
#include <expected>

struct Depths {
    double shallowM;
    double safetyM;
    double deepM;
};

// Smallest value in `valdco` (ascending, may be empty) that is >= safetyM, else safetyM.
double safetyContour(const QList<double>& valdco, double safetyM);

// For each layer in metadata.cheekymarine.depths.layers present in the style: a copy of its filter
// with depth literals mapped from the style's own depths to `target` (and the depcnt-safety contour
// to `safetyContourM`). A depth literal the rule cannot map is an error naming layer and value.
std::expected<QHash<QString, QJsonValue>, QString> depthFilters(const QJsonObject& style, const Depths& target,
                                                                double safetyContourM);
