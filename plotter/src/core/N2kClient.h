#pragma once
#include <QByteArray>
#include <QList>
#include <QLocalSocket>
#include <QObject>
#include <QString>
#include <QTimer>

#include "VesselState.h"

class N2kClient : public QObject {
    Q_OBJECT
public:
    explicit N2kClient(QString socketPath, int staleMs = 3000, int reconnectMs = 2000, QObject *parent = nullptr);
    ~N2kClient() override;
    void start();
    // Milliseconds until the connection goes stale, -1 when the stale timer is not running (a seam for
    // the tests).
    int staleRemainingMs() const { return m_staleTimer.remainingTime(); }

signals:
    void vessel(const VesselState &s);
    void ais(const QList<AisTarget> &targets);
    void connectionChanged(bool live);
    void daemonVersion(const QString &version);
    void schemaMismatch(int schema);

private:
    void connectNow();
    void onReadyRead();
    void onDisconnected();
    void handleLine(const QByteArray &line);
    void setLive(bool live);

    QString m_path;
    int m_staleMs, m_reconnectMs;
    QLocalSocket m_sock;
    QTimer m_staleTimer, m_reconnectTimer;
    QByteArray m_buf;
    bool m_live = false;
    bool m_mismatch = false;
    bool m_helloSeen = false;
    bool m_preHelloWarned = false; // the data-before-hello warning was logged on this connection
};
