#include "AppInfo.h"
#include "N2kClient.h"
#include "plotter/Version.h"
#include <QFile>
#include <QSettings>
#include <algorithm>

namespace {
QVariantMap summary(const PackInfo& p) {
    return {{"kind", p.kind}, {"region", p.region}, {"version", p.version.toString()}, {"notice", p.notice},
            {"onDisk", p.onDisk}};
}
} // namespace

AppInfo::AppInfo(const QList<PackInfo>& scanned, const QList<PackInfo>& inUse, const QString& setVersion,
                 const QStringList& packNotices, const QVariantMap& packModes, const QStringList& dataNotices, QObject* parent)
    : QObject(parent), m_setVersion(setVersion), m_packNotices(packNotices), m_packModes(packModes),
      m_dataNotices(dataNotices) {
    QList<PackInfo> sorted = inUse;
    std::stable_sort(sorted.begin(), sorted.end(), [](const PackInfo& a, const PackInfo& b) {
        if (a.kind != b.kind) return a.kind == QLatin1String("charts");
        return a.region < b.region;
    });
    for (const PackInfo& p : sorted)
        m_inUse.append(summary(p));
    for (const PackInfo& p : scanned) {
        QVariantMap m = summary(p);
        m.insert("refused", p.refused);
        m.insert("inUse", std::any_of(inUse.begin(), inUse.end(), [&](const PackInfo& u) { return u.dir == p.dir; }));
        m_packs.append(m);
    }
}

QString readSetVersion(const QString& lockPath) {
    if (!QFile::exists(lockPath)) return {};
    const QSettings lock(lockPath, QSettings::IniFormat);
    const QString schema = lock.value(QStringLiteral("schema")).toString();
    return schema == QLatin1String("1") || schema == QLatin1String("2")
               ? lock.value(QStringLiteral("set")).toString() : QString();
}

QString AppInfo::appVersion() const { return QString::fromLatin1(kPlotterVersion); }

void AppInfo::setDaemonVersion(const QString& version) {
    if (version != m_daemonVersion) {
        m_daemonVersion = version;
        emit daemonVersionChanged();
    }
    if (m_schemaMismatch) {
        m_schemaMismatch = false;
        emit schemaMismatchChanged();
    }
}

void AppInfo::setSchemaMismatch(int) {
    if (m_schemaMismatch) return;
    m_schemaMismatch = true;
    emit schemaMismatchChanged();
}

void connectAppInfo(N2kClient& client, AppInfo& info) {
    QObject::connect(&client, &N2kClient::daemonVersion, &info, &AppInfo::setDaemonVersion);
    QObject::connect(&client, &N2kClient::schemaMismatch, &info, &AppInfo::setSchemaMismatch);
}

QString platformProblem(const QString& platformName) {
    if (platformName == QLatin1String("offscreen") || platformName == QLatin1String("minimal"))
        return QStringLiteral("renders need a GL display: QT_QPA_PLATFORM %1 cannot draw the chart").arg(platformName);
    return {};
}
