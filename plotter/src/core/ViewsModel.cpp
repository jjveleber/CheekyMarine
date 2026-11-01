#include "ViewsModel.h"
#include "Settings.h"
#include "Store.h"
#include <QDebug>
#include <QJsonDocument>
#include <QSqlError>
#include <QSqlQuery>
#include <QUuid>
#include <algorithm>
#include <utility>

namespace {
QString jsonText(const View& v) { return QString::fromUtf8(QJsonDocument(viewToJson(v)).toJson(QJsonDocument::Compact)); }

QVariantList slotRows(const View& v) {
    QVariantList l;
    for (const ViewSlot& s : v.slotList)
        l.append(QVariantMap{{"id", slotIdName(s.id)}, {"on", s.on}, {"field", fieldName(s.field)}, {"sizeMm", s.sizeMm}});
    return l;
}

QStringList cellFields(const View& v) {
    QStringList l;
    for (Field f : v.cells.fields) l << fieldName(f);
    return l;
}
} // namespace

ViewsModel::ViewsModel(Store& store, Settings& settings, std::function<qint64()> nowSecs, QObject* parent)
    : QAbstractListModel(parent), m_store(store), m_settings(settings), m_now(std::move(nowSecs)) {
    QSqlQuery q(m_store.db());
    if (!q.exec(QStringLiteral("SELECT id, ord, json FROM views ORDER BY ord")))
        qWarning() << "views: read failed:" << q.lastError().text();
    while (q.next()) {
        View v = viewFromJson(QJsonDocument::fromJson(q.value(2).toString().toUtf8()).object());
        v.id = q.value(0).toString();
        m_views << v;
        m_ords << q.value(1).toLongLong();
    }
    currentFromSettings();
}

int ViewsModel::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : count(); }

QVariant ViewsModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() >= count()) return {};
    const View& v = m_views.at(index.row());
    switch (role) {
    case IdRole: return v.id;
    case NameRole: return v.name;
    case ShortNameRole: return v.shortName;
    case IconRole: return v.icon;
    case ChartRole: return viewChartName(v.chart);
    case FavouriteRole: return v.favourite;
    case OnTabBarRole: return onTabBar(v.id);
    case SlotsRole: return slotRows(v);
    case LayoutRole: return v.cells.layout;
    case CellFieldsRole: return cellFields(v);
    }
    return {};
}

QHash<int, QByteArray> ViewsModel::roleNames() const {
    return {{IdRole, "id"},         {NameRole, "name"},           {ShortNameRole, "shortName"},
            {IconRole, "icon"},     {ChartRole, "chart"},         {FavouriteRole, "favourite"},
            {OnTabBarRole, "onTabBar"}, {SlotsRole, "slots"},     {LayoutRole, "layout"},
            {CellFieldsRole, "cellFields"}};
}

void ViewsModel::setCurrentId(const QString& id) {
    if (indexOf(id) < 0) return;
    setCurrent(id, true);
}

void ViewsModel::setCurrent(const QString& id, bool persist) {
    if (persist) m_settings.setLastViewId(id);
    if (id == m_currentId) return;
    m_currentId = id;
    emit currentIdChanged();
}

void ViewsModel::currentFromSettings() {
    const QString last = m_settings.lastViewId();
    setCurrent(indexOf(last) >= 0 ? last : m_views.isEmpty() ? QString() : m_views.first().id, false);
}

void ViewsModel::setFavouriteCapacity(int capacity) {
    if (capacity == m_capacity) return;
    m_capacity = capacity;
    emit favouriteCapacityChanged();
    tabsChanged();
}

QVariantList ViewsModel::tabViews() const {
    QVariantList l;
    for (const View& v : m_views) {
        if (l.size() >= m_capacity) break;
        if (v.favourite) l.append(QVariantMap{{"id", v.id}, {"shortName", v.shortName}, {"icon", v.icon}});
    }
    return l;
}

std::optional<View> ViewsModel::view(const QString& id) const {
    const int i = indexOf(id);
    return i < 0 ? std::nullopt : std::optional<View>(m_views.at(i));
}

int ViewsModel::indexOf(const QString& id) const {
    for (int i = 0; i < count(); ++i)
        if (m_views.at(i).id == id) return i;
    return -1;
}

QVariantMap ViewsModel::viewJson(const QString& id) const {
    const auto v = view(id);
    return v ? viewToJson(*v).toVariantMap() : QVariantMap();
}

bool ViewsModel::onTabBar(const QString& id) const {
    for (const QVariant& t : tabViews())
        if (t.toMap().value("id").toString() == id) return true;
    return false;
}

QString ViewsModel::idOfShort(const QString& shortName) const {
    for (const View& v : m_views)
        if (v.shortName == shortName) return v.id;
    return {};
}

QString ViewsModel::add() {
    const auto taken = [this](const QString& name) {
        for (const View& v : m_views)
            if (v.name == name) return true;
        return false;
    };
    View v;
    for (int n = count() + 1;; ++n) {
        v.name = QStringLiteral("View %1").arg(n);
        if (!taken(v.name)) break;
    }
    v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    v.shortName = shortFromName(v.name);
    v.icon = iconNames().first();
    v.chart = ViewChart::Nav;
    v.slotList = defaultViewSlots();
    for (ViewSlot& s : v.slotList) s.on = false;
    v.cells = viewFromJson({}).cells; // two columns, Depth and SOG
    v.created = v.modified = m_now();
    const qint64 ord = m_ords.isEmpty() ? 0 : m_ords.last() + 1;
    if (!insertView(v, ord)) return {};
    beginInsertRows({}, count(), count());
    m_views << v;
    m_ords << ord;
    endInsertRows();
    emit countChanged();
    tabsChanged();
    return v.id;
}

QString ViewsModel::duplicate(const QString& id) {
    const int i = indexOf(id);
    if (i < 0) return {};
    View v = m_views.at(i);
    v.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    v.name = duplicateName(v.name);
    v.shortName = shortFromName(v.name);
    v.created = v.modified = m_now();
    const qint64 ord = m_ords.at(i) + 1;
    QSqlDatabase db = m_store.db();
    if (!db.transaction()) return {};
    QSqlQuery q(db);
    q.prepare(QStringLiteral("UPDATE views SET ord = ord + 1 WHERE ord >= ?"));
    q.addBindValue(ord);
    if (!q.exec() || !insertView(v, ord) || !db.commit()) {
        qWarning() << "views: duplicate failed:" << q.lastError().text() << db.lastError().text();
        db.rollback();
        return {};
    }
    beginInsertRows({}, i + 1, i + 1);
    for (int j = i + 1; j < count(); ++j)
        if (m_ords[j] >= ord) ++m_ords[j];
    m_views.insert(i + 1, v);
    m_ords.insert(i + 1, ord);
    endInsertRows();
    emit countChanged();
    tabsChanged();
    return v.id;
}

bool ViewsModel::remove(const QString& id) {
    const int i = indexOf(id);
    if (i < 0 || count() == 1) return false;
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("DELETE FROM views WHERE id = ?"));
    q.addBindValue(id);
    if (!q.exec()) {
        qWarning() << "views: remove failed:" << q.lastError().text();
        return false;
    }
    const QString next = m_views.at(i + 1 < count() ? i + 1 : i - 1).id;
    beginRemoveRows({}, i, i);
    m_views.removeAt(i);
    m_ords.removeAt(i);
    endRemoveRows();
    emit countChanged();
    if (id == m_currentId) setCurrent(next, true);
    tabsChanged();
    return true;
}

void ViewsModel::move(const QString& id, int delta) {
    const int i = indexOf(id);
    if (i < 0 || (delta != -1 && delta != 1)) return;
    const int j = i + delta;
    if (j < 0 || j >= count()) return;
    QSqlDatabase db = m_store.db();
    if (!db.transaction()) return;
    QSqlQuery q(db);
    bool ok = true;
    for (const auto& [row, ord] : {std::pair{i, m_ords[j]}, std::pair{j, m_ords[i]}}) {
        q.prepare(QStringLiteral("UPDATE views SET ord = ? WHERE id = ?"));
        q.addBindValue(ord);
        q.addBindValue(m_views[row].id);
        ok = ok && q.exec();
    }
    if (!ok || !db.commit()) {
        qWarning() << "views: move failed:" << q.lastError().text() << db.lastError().text();
        db.rollback();
        return;
    }
    const int top = std::min(i, j);
    beginMoveRows({}, top + 1, top + 1, {}, top); // the lower row of the pair goes above the upper
    m_views.swapItemsAt(i, j);
    endMoveRows();
    tabsChanged();
}

void ViewsModel::setFavourite(const QString& id, bool on) {
    const int i = indexOf(id);
    if (i < 0 || m_views[i].favourite == on) return;
    View v = m_views[i];
    v.favourite = on;
    if (!writeView(v)) return;
    m_views[i] = v;
    tabsChanged();
}

bool ViewsModel::save(const View& view) {
    const int i = indexOf(view.id);
    if (i < 0) return false;
    View v = view;
    const View& old = m_views.at(i);
    v.name = v.name.left(kMaxNameChars);
    v.shortName = v.shortName.left(kMaxShortChars);
    if (v.shortName.isEmpty()) v.shortName = shortFromName(v.name);
    v.created = old.created;
    v.modified = m_now();
    v.extra = old.extra;
    for (auto it = view.extra.begin(); it != view.extra.end(); ++it) v.extra.insert(it.key(), it.value());
    if (!writeView(v)) return false;
    m_views[i] = v;
    emit dataChanged(index(i), index(i));
    tabsChanged();
    return true;
}

bool ViewsModel::saveJson(const QVariantMap& json) { return save(viewFromJson(QJsonObject::fromVariantMap(json))); }

void ViewsModel::replaceAll(const QList<View>& views) {
    QSqlDatabase db = m_store.db();
    if (!db.transaction()) return;
    QSqlQuery q(db);
    bool ok = q.exec(QStringLiteral("DELETE FROM views"));
    for (int i = 0; ok && i < views.size(); ++i) ok = insertView(views[i], i);
    if (!ok || !db.commit()) {
        qWarning() << "views: replace failed:" << q.lastError().text() << db.lastError().text();
        db.rollback();
        return;
    }
    const int before = count();
    beginResetModel();
    m_views = views;
    m_ords.clear();
    for (int i = 0; i < views.size(); ++i) m_ords << i;
    endResetModel();
    if (count() != before) emit countChanged();
    currentFromSettings();
    emit tabViewsChanged();
}

bool ViewsModel::writeView(const View& v) {
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("UPDATE views SET json = ? WHERE id = ?"));
    q.addBindValue(jsonText(v));
    q.addBindValue(v.id);
    if (q.exec()) return true;
    qWarning() << "views: write failed for" << v.id << q.lastError().text();
    return false;
}

bool ViewsModel::insertView(const View& v, qint64 ord) {
    QSqlQuery q(m_store.db());
    q.prepare(QStringLiteral("INSERT INTO views(id, ord, json) VALUES(?, ?, ?)"));
    q.addBindValue(v.id);
    q.addBindValue(ord);
    q.addBindValue(jsonText(v));
    if (q.exec()) return true;
    qWarning() << "views: insert failed for" << v.id << q.lastError().text();
    return false;
}

void ViewsModel::tabsChanged() {
    if (count() > 0) emit dataChanged(index(0), index(count() - 1), {FavouriteRole, OnTabBarRole});
    emit tabViewsChanged();
}
