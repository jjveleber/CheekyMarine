#pragma once
#include <QColor>
#include <QJsonObject>
#include <QString>
#include <QVariantList>
#include <optional>

// The color of `paintProp` on style layer `layer`. A literal color string is returned as is. For a
// `step` or `match` expression, `output` k >= 0 is the k-th output value (step: the base, then each
// stop's value; match: each case's value, then the fallback), and -1 is the last output (the
// fallback). Anything else, or a missing layer, gives none.
std::optional<QColor> styleColour(const QJsonObject& style, const QString& layer, const QString& paintProp,
                                  int output = -1);

// The legend for the `mode` ("nav" or "fish") style `style` in `palette` ("day", "dusk", "night"); an
// empty `style` means no charts pack. `seabed` is the pack's legend.json entries ({abbr, meaning, kind}).
// Categories, in order: ais, navaids (nav only), lights, hazards, depths, seabed; each a map
// {id, title, rows, needsPack}. Without a style only ais has rows and the rest have needsPack true.
// Each row is a map {label, note, kind, color, sprite, tint, iconSize, dash, width, text, depthFrom,
// depthTo, layers}:
// - kind: "sprite" (sheet entry `sprite`, tinted `tint` unless it is empty), "swatch" (fill `color`),
//   "line" (`color`, `width`, `dash`), "text" (sample `text` in `color`), "overlay" (`sprite` is a
//   chartIcons id), "seabed" (`text` is the abbreviation, `label` its meaning).
// - color and tint are "#RRGGBB" (or "#AARRGGBB" for a see-through fill) or empty.
// - depthFrom and depthTo are empty unless the row is a depth band (and empty at an open end): the
//   names "0", "shallow", "safety", "deep" on nav (resolved from the settings), meters on fish
//   (a fish band has an empty label: the sheet shows its range there).
// - layers: the style layer ids the row explains. Rows whose layers are all missing from the style
//   are left out, so the legend shows what the view draws.
QVariantList legendCategories(const QString& mode, const QJsonObject& style, const QString& palette,
                              const QVariantList& seabed);
