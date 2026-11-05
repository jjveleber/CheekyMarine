#pragma once
#include "Views.h"
#include <QAbstractListModel>
#include <QObject>
#include <QVariantMap>

class Settings;
class VesselModel;

// The eight slots of a ViewDraft in SlotId order. `formatted` and `unit` follow vessel and unit
// setting changes; `widestSample` is the field's widestSample, for the page's size clamp.
class DraftSlotsModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QVariantList fieldChoices READ fieldChoicesList CONSTANT)

public:
    enum Role { SlotIdRole = Qt::UserRole + 1, OnRole, FieldRole, FieldLabelRole, SizeMmRole, FormattedRole, UnitRole, WidestSampleRole };

    DraftSlotsModel(VesselModel& vessel, Settings& settings, QObject* parent = nullptr);
    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    void setSlotList(const QList<ViewSlot>& slotList);

private:
    QVariantList fieldChoicesList() const { return fieldChoices(); }

    VesselModel& m_vessel;
    Settings& m_settings;
    QList<ViewSlot> m_slots;
};

// The cells of a ViewDraft, one row per cell of its layout. `formatted` and `unit` as DraftSlotsModel.
class DraftCellsModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QVariantList fieldChoices READ fieldChoicesList CONSTANT)

public:
    enum Role { FieldRole = Qt::UserRole + 1, FieldLabelRole, FormattedRole, UnitRole };

    DraftCellsModel(VesselModel& vessel, Settings& settings, QObject* parent = nullptr);
    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    void setFields(const QList<Field>& fields);

private:
    QVariantList fieldChoicesList() const { return fieldChoices(); }

    VesselModel& m_vessel;
    Settings& m_settings;
    QList<Field> m_fields;
};

// The view being edited. Setters change only the draft; `dirty` says whether anything changed since
// the last load.
class ViewDraft : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString id READ id WRITE setId NOTIFY idChanged)
    Q_PROPERTY(QString name READ name WRITE setName NOTIFY nameChanged)
    Q_PROPERTY(QString shortName READ shortName WRITE setShortName NOTIFY shortNameChanged)
    Q_PROPERTY(QString icon READ icon WRITE setIcon NOTIFY iconChanged)
    Q_PROPERTY(QString chart READ chart WRITE setChart NOTIFY chartChanged)
    Q_PROPERTY(QString layout READ layout WRITE setLayout NOTIFY layoutChanged)
    Q_PROPERTY(bool favorite READ favorite WRITE setFavorite NOTIFY favoriteChanged)
    Q_PROPERTY(bool dirty READ dirty NOTIFY dirtyChanged)
    Q_PROPERTY(QObject* slots READ slotsModel CONSTANT)
    Q_PROPERTY(QObject* cells READ cellsModel CONSTANT)

public:
    // The references must outlive the draft.
    ViewDraft(VesselModel& vessel, Settings& settings, QObject* parent = nullptr);

    QString id() const { return m_view.id; }
    void setId(const QString& id);
    QString name() const { return m_view.name; }
    void setName(const QString& name); // cut to kMaxNameChars
    QString shortName() const { return m_view.shortName; }
    void setShortName(const QString& shortName); // cut to kMaxShortChars; empty allowed while typing
    QString icon() const { return m_view.icon; }
    void setIcon(const QString& icon);
    QString chart() const { return viewChartName(m_view.chart); }
    void setChart(const QString& chart); // nav, fish or none; anything else logged and ignored
    QString layout() const { return m_view.cells.layout; }
    // An invalid key is logged and ignored; a valid one is stored canonical. Fields are kept by order,
    // new cells take defaultCellField, extra fields are dropped.
    void setLayout(const QString& key);
    bool favorite() const { return m_view.favorite; }
    void setFavorite(bool on);
    bool dirty() const { return m_dirty; }
    QObject* slotsModel() const { return m_slotsModel; }
    QObject* cellsModel() const { return m_cellsModel; }

    void load(const View& view);
    // The draft as a view; an empty short name becomes shortFromName(name).
    View toView() const;
    Q_INVOKABLE void loadJson(const QVariantMap& json);
    Q_INVOKABLE QVariantMap toJson() const;
    // Unknown slot id or field: logged and ignored. sizeMm is rounded to 0.1 and floored at kMinSizeMm.
    Q_INVOKABLE void setSlot(const QString& slotId, bool on, const QString& field, double sizeMm);
    // Index outside the layout's cells or unknown field: logged and ignored.
    Q_INVOKABLE void setCellField(int index, const QString& field);

signals:
    void idChanged();
    void nameChanged();
    void shortNameChanged();
    void iconChanged();
    void chartChanged();
    void layoutChanged();
    void favoriteChanged();
    void dirtyChanged();

private:
    void setDirty(bool dirty);

    View m_view;
    bool m_dirty = false;
    DraftSlotsModel* m_slotsModel;
    DraftCellsModel* m_cellsModel;
};
