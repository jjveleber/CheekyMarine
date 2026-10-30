#pragma once
#include "Fields.h"
#include <QAbstractListModel>
#include <QJsonArray>
#include <QList>
#include <QStringView>
#include <QVariantList>
#include <optional>

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
// [{"id":"TL","on":true,"field":"depth","size":"large"}, ...] in SlotId order.
QJsonArray slotsToJson(const QList<SlotConfig>& configs);
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
// Every field in enum order as {name, label} maps, for the QML pickers.
QVariantList fieldChoices();

// The slots for QML, one row per slot in SlotId order. Reads Settings::slotsJson and writes it on
// setSlot. `formatted` and `unit` are refreshed on every vessel change and unit setting change.
class SlotsModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QVariantList fieldChoices READ fieldChoicesList CONSTANT)

public:
    enum Role { SlotIdRole = Qt::UserRole + 1, OnRole, FieldRole, FieldLabelRole, SizeRole, FormattedRole, UnitRole };

    // The references must outlive the model.
    SlotsModel(Settings& settings, VesselModel& vessel, QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    QList<SlotConfig> slotConfigs() const { return m_slots; }
    // Changes one slot and stores all eight. Unknown id, field or size: logged, nothing changes.
    Q_INVOKABLE void setSlot(const QString& id, bool on, const QString& field, const QString& size);
    // Stores the given eight slots (the dev option --slots uses it).
    void setSlotConfigs(const QList<SlotConfig>& configs);

private:
    QVariantList fieldChoicesList() const { return fieldChoices(); }
    void reload();
    void refreshValues();

    Settings& m_settings;
    VesselModel& m_vessel;
    QList<SlotConfig> m_slots;
};
