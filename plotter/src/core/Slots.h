#pragma once
#include "Fields.h"
#include <QJsonArray>
#include <QList>
#include <QStringView>
#include <QVariantList>
#include <functional>
#include <optional>

class QObject;
class Settings;
class VesselModel;

// Overlay slots on the chart page: four corners floating over the chart, and four bars (Top,
// Bottom, Left, Right) that shrink the chart viewport when on.
enum class SlotId { TL, TR, BL, BR, Top, Bottom, Left, Right };
enum class SlotSize { Small, Medium, Large }; // digit heights 8, 14 and 25 mm

struct SlotConfig {
    SlotId id;
    bool on;
    Field field;
    SlotSize size;
    bool operator==(const SlotConfig&) const = default;
};

// The eight slots in SlotId order: TL depth large on, TR sog large on, BL cog medium off,
// BR wtemp medium off, Top time small off, Bottom pos small off, Left stw medium off,
// Right hdg medium off.
QList<SlotConfig> defaultSlots();
// `configs` merged into `stored`: each config's slot gets its on, field and size written into the
// first entry with its id, or appended as {"id":"TL","on":true,"field":"depth","size":"large"} in
// `configs` order. Every other entry and key (a newer app's slot ids, per-slot keys, and the values of
// slots not in `configs`) is kept as is.
QJsonArray slotsToJson(const QList<SlotConfig>& configs, const QJsonArray& stored = {});
// Always the eight slots in SlotId order. A slot with no entry takes its default; within an entry a
// missing or unknown value (on, field, size) takes that slot's default. Unknown ids are ignored;
// for a repeated id the first entry wins.
QList<SlotConfig> slotsFromJson(const QJsonArray& json);

// Stable JSON names: TL TR BL BR Top Bottom Left Right; small medium large.
QString slotIdName(SlotId id);
std::optional<SlotId> slotIdFromName(QStringView name);
QString slotSizeName(SlotSize size);
std::optional<SlotSize> slotSizeFromName(QStringView name);
// Short UI label of a field: "Depth", "SOG", "STW", "COG", "HDG", "Water temp", "Position", "Time", "RPM".
QString fieldLabel(Field field);
// The widest text formatValue can produce for the field, one string per line (Position has two
// lines), for sizing a cell before any value is known.
QString widestSample(Field field);
// Every field in enum order as {name, label} maps, for the QML pickers.
QVariantList fieldChoices();

// Shared by DraftSlotsModel and DraftCellsModel. The `formatted` (unit false) or `unit` (unit true) role of a field.
QString fieldRoleText(Field field, bool unit, const VesselModel& vessel, const Settings& settings);
// Calls `refresh` while `context` lives, whenever a unit setting changes those role texts.
void onUnitSettingsChanged(Settings& settings, QObject* context, const std::function<void()>& refresh);
