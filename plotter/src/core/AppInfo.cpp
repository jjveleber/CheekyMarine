#include "AppInfo.h"
#include "N2kClient.h"
#include "plotter/Version.h"
#include <QFile>
#include <QSettings>

namespace {
QVariantMap summary(const PackInfo& p) {
    return {{"kind", p.kind}, {"region", p.region}, {"version", p.version.toString()}, {"notice", p.notice}};
}
} // namespace

AppInfo::AppInfo(const QList<PackInfo>& packs, const QString& setVersion, QObject* parent)
    : QObject(parent), m_setVersion(setVersion) {
    // The same choice as ChartController: the best charts pack, and the best bathy pack of its region.
    const auto charts = PackCatalog::best(packs, u"charts");
    const auto bathy = charts ? PackCatalog::best(packs, u"bathy", charts->region) : std::nullopt;
    if (charts) m_charts = summary(*charts);
    if (bathy) m_bathy = summary(*bathy);
    for (const PackInfo& p : packs) {
        QVariantMap m = summary(p);
        m.insert("refused", p.refused);
        m.insert("inUse", (charts && p.dir == charts->dir) || (bathy && p.dir == bathy->dir));
        m_packs.append(m);
    }
}

QString readSetVersion(const QString& lockPath) {
    if (!QFile::exists(lockPath)) return {};
    const QSettings lock(lockPath, QSettings::IniFormat);
    return lock.value(QStringLiteral("schema")).toString() == QLatin1String("1")
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
