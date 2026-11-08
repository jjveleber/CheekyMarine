#pragma once
#include "Fields.h"
#include "Store.h"
#include <QHash>
#include <QJsonValue>
#include <QObject>
#include <QVariantMap>

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
    Q_PROPERTY(QString lastPalette READ lastPalette WRITE setLastPalette NOTIFY lastPaletteChanged)
    Q_PROPERTY(QString lastViewId READ lastViewId WRITE setLastViewId NOTIFY lastViewIdChanged)
    Q_PROPERTY(int tabBarHideS READ tabBarHideS WRITE setTabBarHideS NOTIFY tabBarHideSChanged)
    Q_PROPERTY(bool showChartNotice READ showChartNotice WRITE setShowChartNotice NOTIFY showChartNoticeChanged)
    Q_PROPERTY(double panelDiagonalIn READ panelDiagonalIn WRITE setPanelDiagonalIn NOTIFY panelDiagonalInChanged)
    Q_PROPERTY(bool trackRecording READ trackRecording WRITE setTrackRecording NOTIFY trackRecordingChanged)
    Q_PROPERTY(int trackIntervalS READ trackIntervalS WRITE setTrackIntervalS NOTIFY trackIntervalSChanged)
    Q_PROPERTY(double trackMinDistanceM READ trackMinDistanceM WRITE setTrackMinDistanceM NOTIFY trackMinDistanceMChanged)
    Q_PROPERTY(bool showHeadingLine READ showHeadingLine WRITE setShowHeadingLine NOTIFY showHeadingLineChanged)
    Q_PROPERTY(bool showCogLine READ showCogLine WRITE setShowCogLine NOTIFY showCogLineChanged)
    Q_PROPERTY(int cogLineMin READ cogLineMin WRITE setCogLineMin NOTIFY cogLineMinChanged)
    Q_PROPERTY(QString trackLineType READ trackLineType WRITE setTrackLineType NOTIFY trackLineTypeChanged)
    Q_PROPERTY(QString trackColor READ trackColor WRITE setTrackColor NOTIFY trackColorChanged)
    Q_PROPERTY(QStringList legendOpenIds READ legendOpenIds WRITE setLegendOpenIds NOTIFY legendOpenIdsChanged)

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
    QString lastPalette() const { return str("lastPalette"); }
    QString lastViewId() const { return str("lastViewId"); }
    int tabBarHideS() const { return m_v.value("tabBarHideS").toInt(); }
    bool showChartNotice() const { return m_v.value("showChartNotice").toBool(); }
    double panelDiagonalIn() const { return m_v.value("panelDiagonalIn").toDouble(); }
    bool trackRecording() const { return m_v.value("trackRecording").toBool(); }
    int trackIntervalS() const { return m_v.value("trackIntervalS").toInt(); }
    double trackMinDistanceM() const { return m_v.value("trackMinDistanceM").toDouble(); }
    bool showHeadingLine() const { return m_v.value("showHeadingLine").toBool(); }
    bool showCogLine() const { return m_v.value("showCogLine").toBool(); }
    int cogLineMin() const { return m_v.value("cogLineMin").toInt(); }
    QString trackLineType() const { return str("trackLineType"); }
    QString trackColor() const { return str("trackColor"); }
    QStringList legendOpenIds() const;

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
    void setLastPalette(const QString& v) { if (put("lastPalette", v)) emit lastPaletteChanged(); }
    void setLastViewId(const QString& v) { if (put("lastViewId", v)) emit lastViewIdChanged(); }
    void setTabBarHideS(int v) { if (put("tabBarHideS", v)) emit tabBarHideSChanged(); }
    void setShowChartNotice(bool v) { if (put("showChartNotice", v)) emit showChartNoticeChanged(); }
    void setPanelDiagonalIn(double v) { if (put("panelDiagonalIn", v)) emit panelDiagonalInChanged(); }
    void setTrackRecording(bool v) { if (put("trackRecording", v)) emit trackRecordingChanged(); }
    void setTrackIntervalS(int v) { if (put("trackIntervalS", v)) emit trackIntervalSChanged(); }
    void setTrackMinDistanceM(double v) { if (put("trackMinDistanceM", v)) emit trackMinDistanceMChanged(); }
    void setShowHeadingLine(bool v) { if (put("showHeadingLine", v)) emit showHeadingLineChanged(); }
    void setShowCogLine(bool v) { if (put("showCogLine", v)) emit showCogLineChanged(); }
    void setCogLineMin(int v) { if (put("cogLineMin", v)) emit cogLineMinChanged(); }
    void setTrackLineType(const QString& v) { if (put("trackLineType", v)) emit trackLineTypeChanged(); }
    void setTrackColor(const QString& v) { if (put("trackColor", v)) emit trackColorChanged(); }
    void setLegendOpenIds(const QStringList& v);

    // Validates and writes the three depth keys in one transaction. False (nothing changed) if not
    // kMinDepthM <= shallow < safety < deep <= kMaxDepthM.
    Q_INVOKABLE bool setDepths(double shallowM, double safetyM, double deepM);

    // Why setDepths would refuse these values, or an empty map if it would accept them: {code} with
    // code belowMin or aboveMax (plus limitM, the limit in metres), shallowSafety (shallow is not
    // less than safety) or safetyDeep (safety is not less than deep). The page words it in its unit.
    Q_INVOKABLE static QVariantMap depthsProblem(double shallowM, double safetyM, double deepM);

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
    void lastPaletteChanged();
    void lastViewIdChanged();
    void tabBarHideSChanged();
    void showChartNoticeChanged();
    void panelDiagonalInChanged();
    void trackRecordingChanged();
    void trackIntervalSChanged();
    void trackMinDistanceMChanged();
    void showHeadingLineChanged();
    void showCogLineChanged();
    void cogLineMinChanged();
    void trackLineTypeChanged();
    void trackColorChanged();
    void legendOpenIdsChanged();

private:
    QString str(const char* key) const { return m_v.value(key).toString(); }
    bool put(const QString& key, const QJsonValue& v); // true if the value changed and was stored
    bool write(const QString& key, const QJsonValue& v); // upsert, no cache update

    Store& m_store;
    QHash<QString, QJsonValue> m_v;
};
