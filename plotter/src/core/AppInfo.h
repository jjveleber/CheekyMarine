#pragma once
#include "PackCatalog.h"
#include <QObject>
#include <QString>
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
    // The packs in use (the chart controller's choice): {kind, region, version, notice}, charts first,
    // then bathy, then by region; empty if none.
    Q_PROPERTY(QVariantList packsInUse READ packsInUse CONSTANT)
    // ChartController::packNotice: set when the packs are not merged; empty otherwise.
    Q_PROPERTY(QString packNotice READ packNotice CONSTANT)

public:
    // `scanned` is every pack found; `inUse` the ones the loaded styles read (ChartController::packsInUse).
    explicit AppInfo(const QList<PackInfo>& scanned, const QList<PackInfo>& inUse = {}, const QString& setVersion = {},
                     const QString& packNotice = {}, QObject* parent = nullptr);

    QString appVersion() const;
    QString setVersion() const { return m_setVersion; }
    QString daemonVersion() const { return m_daemonVersion; }
    bool schemaMismatch() const { return m_schemaMismatch; }
    QVariantList packs() const { return m_packs; }
    QVariantList packsInUse() const { return m_inUse; }
    QString packNotice() const { return m_packNotice; }

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
    QString m_packNotice;
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
