#include "N2kClient.h"

#include <QJsonDocument>
#include <QJsonObject>

#include "N2kParse.h"

N2kClient::N2kClient(QString socketPath, int staleMs, int reconnectMs, QObject *parent)
    : QObject(parent), m_path(std::move(socketPath)), m_staleMs(staleMs), m_reconnectMs(reconnectMs) {
    m_staleTimer.setSingleShot(true);
    m_reconnectTimer.setSingleShot(true);
    connect(&m_staleTimer, &QTimer::timeout, this, [this] { setLive(false); });
    connect(&m_reconnectTimer, &QTimer::timeout, this, &N2kClient::connectNow);
    connect(&m_sock, &QLocalSocket::readyRead, this, &N2kClient::onReadyRead);
    connect(&m_sock, &QLocalSocket::disconnected, this, &N2kClient::onDisconnected);
    // A failed connect attempt emits errorOccurred but no disconnected(); retry from there. PeerClosedError
    // is always followed by disconnected().
    connect(&m_sock, &QLocalSocket::errorOccurred, this, [this](QLocalSocket::LocalSocketError e) {
        if (e == QLocalSocket::PeerClosedError) return;
        m_sock.abort();
        onDisconnected();
    });
}

N2kClient::~N2kClient() { m_sock.disconnect(this); }

void N2kClient::start() { connectNow(); }

void N2kClient::connectNow() {
    if (m_sock.state() != QLocalSocket::UnconnectedState) return;
    m_buf.clear();
    m_mismatch = false;
    m_helloSeen = false;
    m_sock.connectToServer(m_path);
}

void N2kClient::onDisconnected() {
    // A trailing fragment without a newline may be truncated (slow-client cutoff): drop it.
    m_buf.clear();
    m_staleTimer.stop();
    setLive(false);
    if (!m_reconnectTimer.isActive()) m_reconnectTimer.start(m_reconnectMs);
}

void N2kClient::setLive(bool live) {
    if (m_live == live) return;
    m_live = live;
    emit connectionChanged(live);
}

void N2kClient::onReadyRead() {
    m_buf += m_sock.readAll();
    qsizetype nl;
    while ((nl = m_buf.indexOf('\n')) >= 0) {
        const QByteArray line = m_buf.left(nl);
        m_buf.remove(0, nl + 1);
        if (!line.trimmed().isEmpty()) handleLine(line);
    }
}

void N2kClient::handleLine(const QByteArray &line) {
    QJsonParseError pe;
    const QJsonDocument doc = QJsonDocument::fromJson(line, &pe);
    if (pe.error != QJsonParseError::NoError || !doc.isObject()) {
        qWarning("n2kd: bad line skipped: %s", qPrintable(pe.errorString()));
        return;
    }
    const QJsonObject o = doc.object();
    const QString type = o.value("type").toString();
    if (type == "hello") {
        const auto schema = parseHello(o);
        if (!schema) {
            qWarning("n2kd: bad hello: %s", qPrintable(schema.error()));
            return;
        }
        m_helloSeen = true;
        emit daemonVersion(o.value("version").toString());
        if (*schema != 1) {
            m_mismatch = true;
            emit schemaMismatch(*schema);
        }
    } else if (!m_helloSeen || m_mismatch) {
        return;
    } else if (type == "vessel") {
        const auto v = parseVessel(o);
        if (!v) {
            qWarning("n2kd: bad vessel line skipped: %s", qPrintable(v.error()));
            return;
        }
        m_staleTimer.start(m_staleMs);
        setLive(true);
        emit vessel(*v);
    } else if (type == "ais") {
        const auto a = parseAis(o);
        if (!a) {
            qWarning("n2kd: bad ais line skipped: %s", qPrintable(a.error()));
            return;
        }
        emit ais(*a);
    }
}
