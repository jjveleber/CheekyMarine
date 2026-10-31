#include "Recovery.h"

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
    // Any file left in place (a -wal would be replayed into a new file) stops the open.
    const auto moved = Store::moveAside(m_dir);
    if (!moved) {
        setError(QStringLiteral("%1, so nothing was opened. Check that %2 is writable, then try again.")
                     .arg(moved.error(), m_dir));
        return;
    }
    m_movedTo = *moved;
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
