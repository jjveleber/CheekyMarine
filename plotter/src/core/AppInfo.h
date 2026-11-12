#pragma once
#include "PackCatalog.h"
#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>

class N2kClient;

// What the splash, the About page and the no-data banner show: versions, packs and the daemon's
// schema state.
class AppInfo : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString appVersion READ appVersion CONSTANT)
    Q_PROPERTY(QString daemonVersion READ daemonVersion NOTIFY daemonVersionChanged)
    // The version of the set this binary belongs to, or empty when it is not installed from a set.
    Q_PROPERTY(QString setVersion READ setVersion CONSTANT)
    Q_PROPERTY(bool schemaMismatch READ schemaMismatch NOTIFY schemaMismatchChanged)
    // Every scanned pack: {kind, region, version, notice, refused, inUse}.
    Q_PROPERTY(QVariantList packs READ packs CONSTANT)
    // The packs shown (ChartController::packsInUse): {kind, region, version, notice, onDisk}, charts
    // first, then bathy, then by region; empty if none. onDisk is false for a merged member whose dir is gone.
    Q_PROPERTY(QVariantList packsInUse READ packsInUse CONSTANT)
    // ChartController::packNotices: one line per difference between the installed packs and the files shown.
    Q_PROPERTY(QStringList packNotices READ packNotices CONSTANT)
    // ChartController::packModes: per kind "single", "merged", "merged-stale" or "single-fallback".
    // ChartController::dataNotices: the data licence notices (the CHS notice) of the files shown, shown in full in About.
    Q_PROPERTY(QStringList dataNotices READ dataNotices CONSTANT)
    Q_PROPERTY(QVariantMap packModes READ packModes CONSTANT)

public:
    // `scanned` is every pack found; `inUse` the ones the loaded styles read (ChartController::packsInUse).
    explicit AppInfo(const QList<PackInfo>& scanned, const QList<PackInfo>& inUse = {}, const QString& setVersion = {},
                     const QStringList& packNotices = {}, const QVariantMap& packModes = {},
                     const QStringList& dataNotices = {}, QObject* parent = nullptr);

    QString appVersion() const;
    QString setVersion() const { return m_setVersion; }
    QString daemonVersion() const { return m_daemonVersion; }
    bool schemaMismatch() const { return m_schemaMismatch; }
    QVariantList packs() const { return m_packs; }
    QVariantList packsInUse() const { return m_inUse; }
    QStringList packNotices() const { return m_packNotices; }
    QVariantMap packModes() const { return m_packModes; }
    QStringList dataNotices() const { return m_dataNotices; }

public slots:
    // From N2kClient::daemonVersion (every hello). A new hello clears an earlier mismatch: the
    // client emits schemaMismatch right after the hello when it still applies.
    void setDaemonVersion(const QString& version);
    // From N2kClient::schemaMismatch.
    void setSchemaMismatch(int schema);

signals:
    void daemonVersionChanged();
    void schemaMismatchChanged();

private:
    QString m_setVersion;
    QString m_daemonVersion;
    bool m_schemaMismatch = false;
    QVariantList m_packs;
    QVariantList m_inUse;
    QStringList m_packNotices;
    QVariantMap m_packModes;
    QStringList m_dataNotices;
};

// The `set` of a cheekymarine.lock (installer/README.md, "Lock format"), or empty when the file is
// missing or its schema is not 1 or 2.
QString readSetVersion(const QString& lockPath);

// Forwards the client's hello version and schema mismatch to `info`. The client emits the hello's
// version before a schema mismatch.
void connectAppInfo(N2kClient& client, AppInfo& info);

// Why the chart cannot draw on this Qt platform, or empty when it can (the offscreen and minimal
// platforms have no GL, and cheekyplotter crashes on them).
QString platformProblem(const QString& platformName);
