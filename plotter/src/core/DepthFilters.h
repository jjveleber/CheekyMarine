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

// For each layer in metadata.cheekymarine.depths.layers: a copy of its filter with depth literals
// mapped from the style's own depths to `target` (and the depcnt-safety contour to `safetyContourM`).
// Errors (each names the layer): a listed layer absent from the style, a depth literal the rule cannot
// map, and a depth read in any expression other than a plain binary comparison that also holds a
// numeric literal.
std::expected<QHash<QString, QJsonValue>, QString> depthFilters(const QJsonObject& style, const Depths& target,
                                                                double safetyContourM);
