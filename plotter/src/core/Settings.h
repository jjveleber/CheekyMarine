#pragma once
#include "Fields.h"
#include "Store.h"
#include <QHash>
#include <QJsonValue>
#include <QObject>
#include <QStringList>

// Typed view of the settings table (value column is JSON text). Every set writes immediately; a
// NOTIFY fires only when the value really changed. Keys this version does not know are never touched.
class Settings : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString depthUnit READ depthUnit WRITE setDepthUnit NOTIFY depthUnitChanged)
    Q_PROPERTY(QString speedUnit READ speedUnit WRITE setSpeedUnit NOTIFY speedUnitChanged)
    Q_PROPERTY(QString tempUnit READ tempUnit WRITE setTempUnit NOTIFY tempUnitChanged)
    Q_PROPERTY(bool applyDepthOffset READ applyDepthOffset WRITE setApplyDepthOffset NOTIFY applyDepthOffsetChanged)
    Q_PROPERTY(double shallowM READ shallowM WRITE setShallowM NOTIFY shallowMChanged)
    Q_PROPERTY(double safetyM READ safetyM WRITE setSafetyM NOTIFY safetyMChanged)
    Q_PROPERTY(double deepM READ deepM WRITE setDeepM NOTIFY deepMChanged)
    Q_PROPERTY(QString orientation READ orientation WRITE setOrientation NOTIFY orientationChanged)
    Q_PROPERTY(QString paletteMode READ paletteMode WRITE setPaletteMode NOTIFY paletteModeChanged)
    Q_PROPERTY(QString chartMode READ chartMode WRITE setChartMode NOTIFY chartModeChanged)
    Q_PROPERTY(int touchLockTimeoutS READ touchLockTimeoutS WRITE setTouchLockTimeoutS NOTIFY touchLockTimeoutSChanged)
    Q_PROPERTY(double panelDiagonalIn READ panelDiagonalIn WRITE setPanelDiagonalIn NOTIFY panelDiagonalInChanged)
    Q_PROPERTY(bool trackRecording READ trackRecording WRITE setTrackRecording NOTIFY trackRecordingChanged)
    Q_PROPERTY(int trackIntervalS READ trackIntervalS WRITE setTrackIntervalS NOTIFY trackIntervalSChanged)
    Q_PROPERTY(double trackMinDistanceM READ trackMinDistanceM WRITE setTrackMinDistanceM NOTIFY trackMinDistanceMChanged)
    Q_PROPERTY(QJsonValue slotsJson READ slotsJson WRITE setSlotsJson NOTIFY slotsJsonChanged)
    Q_PROPERTY(QStringList bigNumbers READ bigNumbers WRITE setBigNumbers NOTIFY bigNumbersChanged)

public:
    // The Store must outlive the Settings.
    explicit Settings(Store& store, QObject* parent = nullptr);

    // Depth bounds (metres) are inclusive: 0.5 <= shallow < safety < deep <= 60.
    static constexpr double kMinDepthM = 0.5;
    static constexpr double kMaxDepthM = 60.0;

    QString depthUnit() const { return str("depthUnit"); }
    QString speedUnit() const { return str("speedUnit"); }
    QString tempUnit() const { return str("tempUnit"); }
    bool applyDepthOffset() const { return m_v.value("applyDepthOffset").toBool(); }
    double shallowM() const { return m_v.value("shallowM").toDouble(); }
    double safetyM() const { return m_v.value("safetyM").toDouble(); }
    double deepM() const { return m_v.value("deepM").toDouble(); }
    QString orientation() const { return str("orientation"); }
    QString paletteMode() const { return str("paletteMode"); }
    QString chartMode() const { return str("chartMode"); }
    int touchLockTimeoutS() const { return m_v.value("touchLockTimeoutS").toInt(); }
    double panelDiagonalIn() const { return m_v.value("panelDiagonalIn").toDouble(); }
    bool trackRecording() const { return m_v.value("trackRecording").toBool(); }
    int trackIntervalS() const { return m_v.value("trackIntervalS").toInt(); }
    double trackMinDistanceM() const { return m_v.value("trackMinDistanceM").toDouble(); }
    QJsonValue slotsJson() const { return m_v.value("slots"); }
    QStringList bigNumbers() const;

    // Setters ignore values outside the key's domain (logged) and write nothing for unchanged values.
    void setDepthUnit(const QString& v) { if (put("depthUnit", v)) emit depthUnitChanged(); }
    void setSpeedUnit(const QString& v) { if (put("speedUnit", v)) emit speedUnitChanged(); }
    void setTempUnit(const QString& v) { if (put("tempUnit", v)) emit tempUnitChanged(); }
    void setApplyDepthOffset(bool v) { if (put("applyDepthOffset", v)) emit applyDepthOffsetChanged(); }
    void setShallowM(double v) { setDepths(v, safetyM(), deepM()); }
    void setSafetyM(double v) { setDepths(shallowM(), v, deepM()); }
    void setDeepM(double v) { setDepths(shallowM(), safetyM(), v); }
    void setOrientation(const QString& v) { if (put("orientation", v)) emit orientationChanged(); }
    void setPaletteMode(const QString& v) { if (put("paletteMode", v)) emit paletteModeChanged(); }
    void setChartMode(const QString& v) { if (put("chartMode", v)) emit chartModeChanged(); }
    void setTouchLockTimeoutS(int v) { if (put("touchLockTimeoutS", v)) emit touchLockTimeoutSChanged(); }
    void setPanelDiagonalIn(double v) { if (put("panelDiagonalIn", v)) emit panelDiagonalInChanged(); }
    void setTrackRecording(bool v) { if (put("trackRecording", v)) emit trackRecordingChanged(); }
    void setTrackIntervalS(int v) { if (put("trackIntervalS", v)) emit trackIntervalSChanged(); }
    void setTrackMinDistanceM(double v) { if (put("trackMinDistanceM", v)) emit trackMinDistanceMChanged(); }
    void setSlotsJson(const QJsonValue& v) { if (put("slots", v)) emit slotsJsonChanged(); }
    void setBigNumbers(const QStringList& v);

    // Validates and writes the three depth keys in one transaction. False (nothing changed) if not
    // kMinDepthM <= shallow < safety < deep <= kMaxDepthM.
    Q_INVOKABLE bool setDepths(double shallowM, double safetyM, double deepM);

    UnitPrefs unitPrefs() const;

signals:
    void depthUnitChanged();
    void speedUnitChanged();
    void tempUnitChanged();
    void applyDepthOffsetChanged();
    void shallowMChanged();
    void safetyMChanged();
    void deepMChanged();
    void orientationChanged();
    void paletteModeChanged();
    void chartModeChanged();
    void touchLockTimeoutSChanged();
    void panelDiagonalInChanged();
    void trackRecordingChanged();
    void trackIntervalSChanged();
    void trackMinDistanceMChanged();
    void slotsJsonChanged();
    void bigNumbersChanged();

private:
    QString str(const char* key) const { return m_v.value(key).toString(); }
    bool put(const QString& key, const QJsonValue& v); // true if the value changed and was stored
    bool write(const QString& key, const QJsonValue& v); // upsert, no cache update

    Store& m_store;
    QHash<QString, QJsonValue> m_v;
};
