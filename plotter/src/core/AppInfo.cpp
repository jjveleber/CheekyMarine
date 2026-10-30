#include "AppInfo.h"
#include "plotter/Version.h"

namespace {
QVariantMap summary(const PackInfo& p) {
    return {{"kind", p.kind}, {"region", p.region}, {"version", p.version.toString()}, {"notice", p.notice}};
}
} // namespace

AppInfo::AppInfo(const QList<PackInfo>& packs, QObject* parent) : QObject(parent) {
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
