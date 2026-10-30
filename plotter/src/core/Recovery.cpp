#include "Recovery.h"
#include <QDir>
#include <QFile>

QString storeErrorReason(StoreError e) {
    switch (e) {
    case StoreError::NewerMajor:
        return QStringLiteral("The settings and tracks file was written by a newer version of the app.");
    case StoreError::Corrupt:
        return QStringLiteral("The settings and tracks file is damaged.");
    case StoreError::Io:
        return QStringLiteral("The settings and tracks file could not be opened.");
    }
    return {};
}

Recovery::Recovery(QString dir, StoreError error, QObject* parent)
    : QObject(parent), m_dir(std::move(dir)), m_reason(storeErrorReason(error)), m_canRetry(error == StoreError::Io) {}

void Recovery::startFresh() {
    const QString base = QDir(m_dir).filePath(QStringLiteral("plotter.db"));
    const QString moved = Store::moveAside(m_dir);
    // moveAside returns "" both for nothing to move and for a failed rename, and may move only some
    // of the three files: check the files themselves. A left -wal would be replayed into a new file.
    for (const QString& suffix : {QString(), QStringLiteral("-wal"), QStringLiteral("-shm")}) {
        if (QFile::exists(base + suffix)) {
            setError(QStringLiteral("plotter.db%1 could not be moved aside, so nothing was opened. "
                                    "Check that %2 is writable, then try again.")
                         .arg(suffix, m_dir));
            return;
        }
    }
    m_movedTo = moved;
    take(Store::open(m_dir));
}

void Recovery::retry() { take(Store::open(m_dir)); }

void Recovery::take(std::expected<std::unique_ptr<Store>, StoreError> r) {
    if (!r) {
        setError(QStringLiteral("It still does not open: %1").arg(storeErrorReason(r.error())));
        return;
    }
    m_store = std::move(*r);
    setError(QString());
    emit recovered();
}

void Recovery::setError(const QString& e) {
    if (e == m_error) return;
    m_error = e;
    emit errorChanged();
}
