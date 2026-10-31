#include "core/PaletteController.h"
#include "core/Settings.h"
#include "core/VesselModel.h"
#include <QTimeZone>
#include <cmath>

PaletteController::PaletteController(Settings& settings, VesselModel& vessel, std::function<QDateTime()> nowUtc,
                                     QObject* parent)
    : QObject(parent), m_settings(settings), m_vessel(vessel), m_nowUtc(std::move(nowUtc)),
      m_palette(settings.lastPalette()), m_timer(this) {
    connect(&m_timer, &QTimer::timeout, this, &PaletteController::evaluate);
    connect(&m_settings, &Settings::paletteModeChanged, this, &PaletteController::evaluate);
    connect(&m_vessel, &VesselModel::changed, this, [this] {
        const VesselState& s = m_vessel.state();
        if (!m_hadPosition && s.lat && s.lon) evaluate();
    });
    m_timer.start(kIntervalMs);
    evaluate();
}

void PaletteController::evaluate() {
    const QString mode = m_settings.paletteMode();
    const VesselState& s = m_vessel.state();
    m_hadPosition = s.lat && s.lon;
    if (mode != QLatin1String("auto")) {
        set(mode);
        return;
    }
    if (!m_hadPosition) return; // keep the last palette
    const QDateTime when = s.gnssTime
                               ? QDateTime::fromSecsSinceEpoch(qint64(std::floor(*s.gnssTime)), QTimeZone::UTC)
                               : m_nowUtc();
    set(paletteName(paletteAt(when, *s.lat, *s.lon)));
}

void PaletteController::set(const QString& palette) {
    if (palette == m_palette) return;
    m_palette = palette;
    m_settings.setLastPalette(palette);
    emit paletteChanged();
}
