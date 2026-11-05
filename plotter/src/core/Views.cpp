#include "Views.h"
#include "Tilings.h"
#include <QDebug>
#include <QJsonDocument>
#include <QSqlQuery>
#include <algorithm>
#include <cmath>

namespace {
const QString kDefaultLayout = QStringLiteral("2x2:0,0,1,2;1,0,1,2");

// "favourite" is the legacy key, read until the 1.2.0 migration has run.
const QStringList kKnownKeys{"id", "name", "short", "icon", "chart", "favorite", "favourite", "slots", "cells", "created", "modified"};
const QStringList kKnownSlotKeys{"id", "on", "field", "sizeMm", "size"};

QList<ViewSlot> toViewSlots(const QList<SlotConfig>& configs) {
    QList<ViewSlot> out;
    for (const SlotConfig& c : configs) out << ViewSlot{c.id, c.on, c.field, sizeMmFromSlotSize(c.size)};
    return out;
}

View shippedView(const QString& id, const QString& name, const QString& shortName, const QString& icon,
                 ViewChart chart, qint64 now) {
    View v;
    v.id = id;
    v.name = name;
    v.shortName = shortName;
    v.icon = icon;
    v.chart = chart;
    v.favorite = true;
    v.slotList = defaultViewSlots();
    v.cells = {kDefaultLayout, {Field::Depth, Field::Sog}};
    v.created = v.modified = now;
    return v;
}

int cellCount(const QString& layoutKey) {
    const auto l = layoutFromKey(layoutKey);
    return l ? int(l->cells.size()) : 0;
}
}  // namespace

QString viewChartName(ViewChart c) {
    switch (c) {
    case ViewChart::Nav: return QStringLiteral("nav");
    case ViewChart::Fish: return QStringLiteral("fish");
    case ViewChart::None: return QStringLiteral("none");
    }
    return {};
}

std::optional<ViewChart> viewChartFromName(QStringView n) {
    for (ViewChart c : {ViewChart::Nav, ViewChart::Fish, ViewChart::None})
        if (n == viewChartName(c)) return c;
    return std::nullopt;
}

double sizeMmFromSlotSize(SlotSize s) {
    switch (s) {
    case SlotSize::Small: return 8;
    case SlotSize::Medium: return 14;
    case SlotSize::Large: return 25;
    }
    return 14;
}

QList<ViewSlot> defaultViewSlots() { return toViewSlots(defaultSlots()); }

QStringList iconNames() {
    return {"anchor", "fish", "hash", "sailboat", "ship", "lifebuoy", "map", "compass",
            "gauge",  "sun",  "moon", "ripple",   "flag", "star",    "settings", "home"};
}

Field defaultCellField(int index) {
    static const Field kOrder[] = {Field::Depth, Field::Sog, Field::Stw, Field::Cog, Field::Heading, Field::WaterTemp};
    return index >= 0 && index < 6 ? kOrder[index] : Field::Depth;
}

QString shortFromName(const QString& name) {
    QString s = name;
    s.remove(QLatin1Char(' '));
    s = s.left(kMaxShortChars);
    return s.isEmpty() ? QStringLiteral("View") : s;
}

QString duplicateName(const QString& name) { return (name + QStringLiteral(" 2")).left(kMaxNameChars); }

QJsonObject viewToJson(const View& v) {
    QJsonObject o = v.extra;
    o["id"] = v.id;
    o["name"] = v.name;
    o["short"] = v.shortName;
    o["icon"] = v.icon;
    o["chart"] = viewChartName(v.chart);
    o["favorite"] = v.favorite;
    QJsonArray slotArray;
    for (const ViewSlot& s : v.slotList) {
        QJsonObject so = s.extra;
        so["id"] = slotIdName(s.id);
        so["on"] = s.on;
        so["field"] = fieldName(s.field);
        so["sizeMm"] = s.sizeMm;
        slotArray.append(so);
    }
    o["slots"] = slotArray;
    QJsonArray fields;
    for (Field f : v.cells.fields) fields.append(fieldName(f));
    o["cells"] = QJsonObject{{"layout", v.cells.layout}, {"fields", fields}};
    o["created"] = double(v.created);
    o["modified"] = double(v.modified);
    return o;
}

View viewFromJson(const QJsonObject& o) {
    View v;
    v.id = o.value("id").toString();
    v.name = o.value("name").toString().left(kMaxNameChars);
    if (v.name.isEmpty()) v.name = QStringLiteral("View");
    v.shortName = o.value("short").toString().left(kMaxShortChars);
    if (v.shortName.isEmpty()) v.shortName = shortFromName(v.name);
    v.icon = o.value("icon").toString();
    if (!iconNames().contains(v.icon)) v.icon = iconNames().first();
    v.chart = viewChartFromName(o.value("chart").toString()).value_or(ViewChart::Nav);
    v.favorite = o.contains("favorite") ? o.value("favorite").toBool(false) : o.value("favourite").toBool(false);

    v.slotList = defaultViewSlots();
    QList<bool> seen(v.slotList.size(), false);
    for (const QJsonValue& sv : o.value("slots").toArray()) {
        if (!sv.isObject()) continue;
        const QJsonObject so = sv.toObject();
        const auto id = slotIdFromName(so.value("id").toString());
        if (!id || seen[int(*id)]) continue;
        seen[int(*id)] = true;
        ViewSlot& s = v.slotList[int(*id)];
        if (so.value("on").isBool()) s.on = so.value("on").toBool();
        if (const auto f = fieldFromName(so.value("field").toString())) s.field = *f;
        if (so.value("sizeMm").isDouble()) s.sizeMm = std::max(kMinSizeMm, std::round(so.value("sizeMm").toDouble() * 10.0) / 10.0);
        else if (const auto z = slotSizeFromName(so.value("size").toString())) s.sizeMm = sizeMmFromSlotSize(*z);
        for (auto it = so.begin(); it != so.end(); ++it)
            if (!kKnownSlotKeys.contains(it.key())) s.extra.insert(it.key(), it.value());
    }

    const QJsonObject co = o.value("cells").toObject();
    const auto layout = layoutFromKey(co.value("layout").toString());
    v.cells.layout = layout ? canonicalKey(*layout) : QString();
    if (v.cells.layout.isEmpty()) v.cells.layout = kDefaultLayout;
    const int n = cellCount(v.cells.layout);
    const QJsonArray fa = co.value("fields").toArray();
    for (int i = 0; i < n; ++i)
        v.cells.fields << (i < fa.size() ? fieldFromName(fa.at(i).toString()) : std::nullopt).value_or(defaultCellField(i));

    v.created = qint64(o.value("created").toDouble());
    v.modified = qint64(o.value("modified").toDouble());
    for (auto it = o.begin(); it != o.end(); ++it)
        if (!kKnownKeys.contains(it.key())) v.extra.insert(it.key(), it.value());
    return v;
}

QList<View> shippedViews(qint64 now) {
    return {shippedView("shipped-nav", "Navigation", "Nav", "compass", ViewChart::Nav, now),
            shippedView("shipped-fish", "Fishing", "Fish", "fish", ViewChart::Fish, now),
            shippedView("shipped-big", "Big numbers", "Big #", "hash", ViewChart::None, now)};
}

QList<View> viewsFromPlan3(const QJsonArray& slotsJson, const QStringList& bigNumbers, qint64 now) {
    QList<View> views = shippedViews(now);
    views[0].slotList = toViewSlots(slotsFromJson(slotsJson));
    // slotsFromJson drops unknown slot keys; carry them over, first entry per id wins.
    QList<bool> seen(views[0].slotList.size(), false);
    for (const QJsonValue& sv : slotsJson) {
        if (!sv.isObject()) continue;
        const QJsonObject so = sv.toObject();
        const auto id = slotIdFromName(so.value("id").toString());
        if (!id || seen[int(*id)]) continue;
        seen[int(*id)] = true;
        for (auto it = so.begin(); it != so.end(); ++it)
            if (!kKnownSlotKeys.contains(it.key())) views[0].slotList[int(*id)].extra.insert(it.key(), it.value());
    }
    QList<Field> fields;
    for (int i = 0; i < 4 && (i < bigNumbers.size() || i < 2); ++i)
        fields << (i < bigNumbers.size() ? fieldFromName(bigNumbers.at(i)) : std::nullopt).value_or(defaultCellField(i));
    static const char* const kLayouts[] = {"2x2:0,0,1,2;1,0,1,2", "3x2:0,0,1,2;1,0,1,2;2,0,1,2",
                                           "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"};
    views[2].cells = {QString::fromLatin1(kLayouts[fields.size() - 2]), fields};
    return views;
}

QString viewJsonText(const View& v) { return QString::fromUtf8(QJsonDocument(viewToJson(v)).toJson(QJsonDocument::Compact)); }

QSqlError insertViewRow(QSqlDatabase& db, const View& view, qint64 ord) {
    QSqlQuery q(db);
    q.prepare(QStringLiteral("INSERT INTO views(id, ord, json) VALUES(?, ?, ?)"));
    q.addBindValue(view.id);
    q.addBindValue(ord);
    q.addBindValue(viewJsonText(view));
    if (q.exec()) return {};
    qWarning() << "views: insert failed for" << view.id << q.lastError().text();
    return q.lastError();
}

QSqlError seedViews(QSqlDatabase& db, qint64 now) {
    QSqlQuery q(db);
    if (!q.exec(QStringLiteral("SELECT key, value FROM settings WHERE key IN ('slots', 'bigNumbers')"))) return q.lastError();
    bool plan3 = false;
    QJsonArray slotsJson;
    QStringList bigNumbers;
    while (q.next()) {
        plan3 = true;
        const QString key = q.value(0).toString();
        // Settings stores a bare JSON value; wrapped in [] it parses as a document (Settings::fromText).
        QJsonParseError e;
        const QJsonArray doc = QJsonDocument::fromJson(("[" + q.value(1).toString() + "]").toUtf8(), &e).array();
        if (e.error != QJsonParseError::NoError || doc.size() != 1 || !doc.at(0).isArray()) {
            qWarning() << "views: unusable value for" << key << "- using defaults";
            continue;
        }
        if (key == QLatin1String("slots")) {
            slotsJson = doc.at(0).toArray();
        } else {
            for (const QJsonValue& v : doc.at(0).toArray()) bigNumbers << v.toString();
        }
    }
    const QList<View> views = plan3 ? viewsFromPlan3(slotsJson, bigNumbers, now) : shippedViews(now);
    for (int i = 0; i < views.size(); ++i)
        if (QSqlError e = insertViewRow(db, views[i], i); e.isValid()) return e;
    if (!q.exec(QStringLiteral("DELETE FROM settings WHERE key IN ('slots', 'bigNumbers', 'chartMode', 'touchLockTimeoutS')")))
        return q.lastError();
    return {};
}

int favoriteCapacity(double barHeightMm) { return std::max(0, int(std::floor((barHeightMm - 46) / 16))); }
