#pragma once
#include "Slots.h"
#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QString>
#include <QStringList>
#include <QStringView>
#include <optional>

// Saved views: what the chart page shows (chart mode, overlay slots, big-number cells).
enum class ViewChart { Nav, Fish, None };
QString viewChartName(ViewChart); // nav fish none
std::optional<ViewChart> viewChartFromName(QStringView);

struct ViewSlot {
    SlotId id;
    bool on;
    Field field;
    double sizeMm; // digit height
    bool operator==(const ViewSlot&) const = default;
};

struct ViewCells {
    QString layout; // a Tilings.h layout key
    QList<Field> fields;
    bool operator==(const ViewCells&) const = default;
};

struct View {
    QString id, name, shortName, icon;
    ViewChart chart = ViewChart::Nav;
    bool favourite = false;
    QList<ViewSlot> slotList; // JSON key "slots" (a member named slots is a Qt keyword macro)
    ViewCells cells;
    qint64 created = 0, modified = 0;
    QJsonObject extra; // unknown top-level keys, kept through a round trip
    bool operator==(const View&) const = default;
};

constexpr double kMinSizeMm = 6.0;
constexpr int kMaxNameChars = 24, kMaxShortChars = 6;

double sizeMmFromSlotSize(SlotSize); // 8, 14, 25
// defaultSlots() with sizes mapped: TL depth 25 on, TR sog 25 on, the rest off.
QList<ViewSlot> defaultViewSlots();
// 16 names; a new view takes the first; "home" draws the house tab.
QStringList iconNames();
// Depth, Sog, Stw, Cog, Heading, WaterTemp by index; index 6 and up: Depth.
Field defaultCellField(int index);
// Spaces removed, first 6 characters, "View" when that is empty.
QString shortFromName(const QString& name);
// name + " 2", cut to 24 characters.
QString duplicateName(const QString& name);

// `extra` keys first, then the known keys over them.
QJsonObject viewToJson(const View&);
// A missing or invalid field takes its default; unknown top-level keys go to `extra`.
View viewFromJson(const QJsonObject&);

QList<View> shippedViews(qint64 now);
// The shipped three, with Navigation's slots from the plan 3 slots JSON and Big numbers' cells from
// the plan 3 bigNumbers list (padded with defaults to 2, cut to 4).
QList<View> viewsFromPlan3(const QJsonArray& slotsJson, const QStringList& bigNumbers, qint64 now);

// How many favourites fit a bar of this height.
int favouriteCapacity(double barHeightMm);
