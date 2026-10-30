#pragma once
#include "Fields.h"
#include <QAbstractListModel>
#include <QList>

class Settings;
class VesselModel;

// The big numbers page: 2 to 4 cells from Settings::bigNumbers. A stored name that is unknown takes
// the default of its cell (depth, sog, cog, stw by position); fewer than 2 are padded with those
// defaults and more than 4 are cut. `formatted` and `unit` follow vessel and unit setting changes.
class NumbersModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
    Q_PROPERTY(QVariantList fieldChoices READ fieldChoicesList CONSTANT)

public:
    static constexpr int kMinCells = 2;
    static constexpr int kMaxCells = 4;
    enum Role { FieldRole = Qt::UserRole + 1, FieldLabelRole, FormattedRole, UnitRole };

    // The references must outlive the model.
    NumbersModel(Settings& settings, VesselModel& vessel, QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const { return int(m_fields.size()); }
    QList<Field> fields() const { return m_fields; }
    // Out of range index or unknown name: logged, nothing changes.
    Q_INVOKABLE void setField(int index, const QString& name);
    // n outside 2..4: logged, nothing changes. New cells take their position's default.
    Q_INVOKABLE void setCount(int n);

signals:
    void countChanged();

private:
    QVariantList fieldChoicesList() const;
    void reload();
    void refreshValues();

    Settings& m_settings;
    VesselModel& m_vessel;
    QList<Field> m_fields;
};
