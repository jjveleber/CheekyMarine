#pragma once
#include "core/Sun.h"
#include <QDateTime>
#include <QObject>
#include <QTimer>
#include <functional>

class Settings;
class VesselModel;

// The palette in use ("day", "dusk", "night"). Manual paletteMode values are used as is; "auto"
// follows the sun at the vessel position, at the GNSS time when known, else nowUtc(). Re-evaluated
// every 60 s, on a paletteMode change and when a position arrives after none. Without a position it
// keeps the last palette (initially day).
class PaletteController : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString palette READ palette NOTIFY paletteChanged)

public:
    static constexpr int kIntervalMs = 60000;

    // The references must outlive the controller. Evaluates once at construction.
    PaletteController(Settings& settings, VesselModel& vessel, std::function<QDateTime()> nowUtc,
                      QObject* parent = nullptr);

    QString palette() const { return m_palette; }
    void evaluate();

signals:
    void paletteChanged();

private:
    void set(const QString& palette);

    Settings& m_settings;
    VesselModel& m_vessel;
    std::function<QDateTime()> m_nowUtc;
    QString m_palette = QStringLiteral("day");
    bool m_hadPosition = false; // the last evaluation had a position
    QTimer m_timer;
};
