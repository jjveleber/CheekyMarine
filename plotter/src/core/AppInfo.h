#pragma once
#include "PackCatalog.h"
#include <QObject>
#include <QVariantList>
#include <QVariantMap>

// What the splash, the About page and the no-data banner show: versions, packs and the daemon's
// schema state.
class AppInfo : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString appVersion READ appVersion CONSTANT)
    Q_PROPERTY(QString daemonVersion READ daemonVersion NOTIFY daemonVersionChanged)
    Q_PROPERTY(bool schemaMismatch READ schemaMismatch NOTIFY schemaMismatchChanged)
    // Every scanned pack: {kind, region, version, notice, refused, inUse}.
    Q_PROPERTY(QVariantList packs READ packs CONSTANT)
    // The packs in use (the chart controller's choice): {kind, region, version, notice}; empty if none.
    Q_PROPERTY(QVariantMap chartsPack READ chartsPack CONSTANT)
    Q_PROPERTY(QVariantMap bathyPack READ bathyPack CONSTANT)

public:
    explicit AppInfo(const QList<PackInfo>& packs, QObject* parent = nullptr);

    QString appVersion() const;
    QString daemonVersion() const { return m_daemonVersion; }
    bool schemaMismatch() const { return m_schemaMismatch; }
    QVariantList packs() const { return m_packs; }
    QVariantMap chartsPack() const { return m_charts; }
    QVariantMap bathyPack() const { return m_bathy; }

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
    QString m_daemonVersion;
    bool m_schemaMismatch = false;
    QVariantList m_packs;
    QVariantMap m_charts, m_bathy;
};
