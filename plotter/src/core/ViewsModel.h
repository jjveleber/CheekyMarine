#pragma once
#include "Views.h"
#include <QAbstractListModel>
#include <QList>
#include <QVariantList>
#include <QVariantMap>
#include <functional>
#include <optional>

class Settings;
class Store;

// The saved views, one row per view in `ord` order, backed by the views table (one JSON row per
// view). Every change is written at once. There is always at least one view.
class ViewsModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
    // Writes Settings::lastViewId; an unknown id is ignored.
    Q_PROPERTY(QString currentId READ currentId WRITE setCurrentId NOTIFY currentIdChanged)
    Q_PROPERTY(int favoriteCapacity READ favoriteCapacity WRITE setFavoriteCapacity NOTIFY favoriteCapacityChanged)
    // The first favoriteCapacity favorites in order, as {id, shortName, icon}.
    Q_PROPERTY(QVariantList tabViews READ tabViews NOTIFY tabViewsChanged)

public:
    enum Role {
        IdRole = Qt::UserRole + 1,
        NameRole,
        ShortNameRole,
        IconRole,
        ChartRole,
        FavoriteRole,
        OnTabBarRole,
        SlotsRole, // QVariantList of {id, on, field, sizeMm}
        LayoutRole,
        CellFieldsRole, // QStringList
    };

    // The references must outlive the model. `nowSecs` stamps `modified` (and `created` of new views).
    ViewsModel(Store& store, Settings& settings, std::function<qint64()> nowSecs, QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const { return int(m_views.size()); }
    QString currentId() const { return m_currentId; }
    void setCurrentId(const QString& id);
    int favoriteCapacity() const { return m_capacity; }
    void setFavoriteCapacity(int capacity);
    QVariantList tabViews() const;

    QList<View> views() const { return m_views; }
    std::optional<View> view(const QString& id) const;
    Q_INVOKABLE int indexOf(const QString& id) const;
    // viewToJson as a variant map; empty for an unknown id.
    Q_INVOKABLE QVariantMap viewJson(const QString& id) const;
    Q_INVOKABLE bool onTabBar(const QString& id) const;
    // The id of the first view with this short name, or empty.
    Q_INVOKABLE QString idOfShort(const QString& shortName) const;

    // Appends "View N" (N from count + 1 up to the first free name), every slot off, cells Depth and
    // SOG in two columns, not a favorite. Returns its id.
    Q_INVOKABLE QString add();
    // Inserts a copy right after `id`, named duplicateName; returns its id, or empty for an unknown id.
    Q_INVOKABLE QString duplicate(const QString& id);
    // False for an unknown id or the only view. A removed current view passes current to the next
    // view (the previous one when it was last).
    Q_INVOKABLE bool remove(const QString& id);
    // delta -1 or +1: swaps the view with its neighbour; nothing at the ends.
    Q_INVOKABLE void move(const QString& id, int delta);
    Q_INVOKABLE void setFavorite(const QString& id, bool on);
    // Replaces the view with this id (false when there is none): modified = now; its ord, created and
    // stored extra keys are kept; name and short are cut to their caps, an empty name becomes
    // "View" and an empty short is made from the name.
    bool save(const View& view);
    Q_INVOKABLE bool saveJson(const QVariantMap& json);
    // Every row replaced by `views` in order; current is lastViewId when it names one, else the first.
    // An empty list is refused (logged): there is always at least one view.
    void replaceAll(const QList<View>& views);

signals:
    void countChanged();
    void currentIdChanged();
    void favoriteCapacityChanged();
    void tabViewsChanged();

private:
    bool writeView(const View& v); // UPDATE of an existing row's json
    void setCurrent(const QString& id, bool persist);
    void currentFromSettings();
    void tabsChanged(); // favorite, order or capacity changed: onTabBar of every row and tabViews

    Store& m_store;
    Settings& m_settings;
    std::function<qint64()> m_now;
    QList<View> m_views;
    QList<qint64> m_ords; // the ord column of each row, parallel to m_views
    QString m_currentId;
    int m_capacity = 5;
};
