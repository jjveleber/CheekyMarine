#include <QElapsedTimer>
#include <QLocalServer>
#include <QLocalSocket>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QtTest>

#include "core/AisModel.h"
#include "core/N2kClient.h"
#include "core/VesselModel.h"

Q_DECLARE_METATYPE(VesselState)
Q_DECLARE_METATYPE(QList<AisTarget>)

static const QByteArray kHello = "{\"type\":\"hello\",\"schema\":1,\"version\":\"0.3.0\"}\n";
static const QByteArray kVesselLine =
    "{\"type\":\"vessel\",\"t\":10.5,\"pos\":{\"lat\":47.6,\"lon\":-122.3},\"sog\":3.29,\"cog\":3.7,\"hdg\":3.6,\"hdgRef\":\"True\",\"variation\":0.26,\"depth\":14.4,\"depthOffset\":-0.3,\"stw\":null,\"waterTemp\":287.6,\"gnssTime\":null,\"sats\":null,\"rpm\":null}\n";
static const QByteArray kAisLine =
    "{\"type\":\"ais\",\"t\":10.5,\"targets\":[{\"mmsi\":7,\"class\":\"A\",\"lat\":47.7,\"lon\":-122.4,\"sog\":1.0,\"cog\":1.0,\"hdg\":null,\"name\":\"X\",\"callsign\":null,\"shipType\":null,\"navStatus\":0,\"age\":2.5,\"posAge\":2.5}]}\n";

class TstN2kClient : public QObject {
    Q_OBJECT
    QTemporaryDir m_dir;
    QLocalServer m_server;
    QLocalSocket *m_peer = nullptr;
    QString path() const { return m_dir.filePath("n2k.sock"); }

    void listen() {
        QLocalServer::removeServer(path());
        QVERIFY(m_server.listen(path()));
    }
    // Waits for the client to connect and keeps the accepted socket in m_peer.
    bool accept() {
        // QSignalSpy::wait runs the event loop (waitForNewConnection would block the client's timers).
        QSignalSpy spy(&m_server, &QLocalServer::newConnection);
        if (!m_server.hasPendingConnections() && !spy.wait(10000)) return false;
        m_peer = m_server.nextPendingConnection();
        return m_peer != nullptr;
    }
    void send(const QByteArray &b) {
        m_peer->write(b);
        m_peer->flush();
    }

private slots:
    void init() {
        qRegisterMetaType<VesselState>();
        qRegisterMetaType<QList<AisTarget>>();
        QVERIFY(m_dir.isValid());
        m_peer = nullptr;
        listen();
    }
    void cleanup() {
        m_server.close();
        m_peer = nullptr;
    }

    void helloThenVessel() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy vs(&c, &N2kClient::vessel), cs(&c, &N2kClient::connectionChanged), dv(&c, &N2kClient::daemonVersion);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        QCOMPARE(cs.count(), 1);
        QCOMPARE(cs.first().first().toBool(), true);
        QCOMPARE(dv.first().first().toString(), QString("0.3.0"));
        auto s = vs.first().first().value<VesselState>();
        QCOMPARE(*s.sogMs, 3.29);
        QCOMPARE(s.hdgRef, QString("True"));
    }
    void schemaMismatch() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy vs(&c, &N2kClient::vessel), mm(&c, &N2kClient::schemaMismatch);
        c.start();
        QVERIFY(accept());
        send("{\"type\":\"hello\",\"schema\":2,\"version\":\"9.0.0\"}\n" + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(mm.count(), 1, 10000);
        QCOMPARE(mm.first().first().toInt(), 2);
        QTest::qWait(200);
        QCOMPARE(vs.count(), 0);
    }
    // Data before the first hello of a connection is ignored, on the first connect and after a reconnect.
    void dataBeforeHelloIgnored() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy vs(&c, &N2kClient::vessel), as(&c, &N2kClient::ais), cs(&c, &N2kClient::connectionChanged);
        c.start();
        QVERIFY(accept());
        send(kVesselLine + kAisLine);
        QTest::qWait(200);
        QCOMPARE(vs.count(), 0);
        QCOMPARE(as.count(), 0);
        QCOMPARE(cs.count(), 0);
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        m_peer->disconnectFromServer();
        QTRY_COMPARE_WITH_TIMEOUT(cs.count(), 2, 10000);
        m_peer = nullptr;
        QVERIFY(accept());
        send(kVesselLine);
        QTest::qWait(200);
        QCOMPARE(vs.count(), 1);
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 2, 10000);
    }
    void lineSplitAcrossWrites() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy vs(&c, &N2kClient::vessel);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine.left(40));
        QTest::qWait(100);
        QCOMPARE(vs.count(), 0);
        send(kVesselLine.mid(40));
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        QTest::qWait(100);
        QCOMPARE(vs.count(), 1);
    }
    void aisEmitted() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy as(&c, &N2kClient::ais);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine + kAisLine);
        QTRY_COMPARE_WITH_TIMEOUT(as.count(), 1, 10000);
        QCOMPARE(as.first().first().value<QList<AisTarget>>().first().mmsi, quint32(7));
    }
    void badLineSkipped() {
        N2kClient c(path(), 3000, 100);
        QSignalSpy vs(&c, &N2kClient::vessel);
        c.start();
        QVERIFY(accept());
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression(".*"));
        send(kHello + "not json\n" + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
    }
    // Review Focus 1: a half line at disconnect is never parsed; the client reconnects and data resumes.
    void halfLineAtDisconnectDroppedThenReconnect() {
        const int reconnectMs = 500;
        N2kClient c(path(), 5000, reconnectMs);
        QSignalSpy vs(&c, &N2kClient::vessel), cs(&c, &N2kClient::connectionChanged);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        // A prefix that would be valid JSON up to the cut, then the server drops the client.
        send(kVesselLine.left(kVesselLine.size() - 10));
        QTest::qWait(50);
        m_peer->disconnectFromServer();
        QElapsedTimer t;
        t.start();
        QTRY_COMPARE_WITH_TIMEOUT(cs.count(), 2, 10000);
        QCOMPARE(cs.last().first().toBool(), false);
        QCOMPARE(vs.count(), 1);
        // The server is still listening: the client must reconnect within reconnectMs + 500 ms of the
        // disconnect (timer started just before waiting for it, so the bound only gets stricter).
        m_peer = nullptr;
        QVERIFY(accept());
        const qint64 took = t.elapsed();
        QVERIFY2(took < reconnectMs + 500, qPrintable(QString("reconnect took %1 ms").arg(took)));
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 2, 10000);
        QCOMPARE(cs.last().first().toBool(), true);
    }
    void reconnectAfterServerRestart() {
        const int reconnectMs = 500;
        N2kClient c(path(), 5000, reconnectMs);
        QSignalSpy vs(&c, &N2kClient::vessel), cs(&c, &N2kClient::connectionChanged);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        send(kVesselLine.left(30));
        QTest::qWait(50);
        m_server.close();
        m_peer->disconnectFromServer();
        QTRY_COMPARE_WITH_TIMEOUT(cs.count(), 2, 10000);
        QCOMPARE(vs.count(), 1);
        QTest::qWait(1200);  // a couple of failed reconnect attempts
        listen();
        QElapsedTimer t;
        t.start();
        m_peer = nullptr;
        QVERIFY(accept());
        QVERIFY2(t.elapsed() < reconnectMs + 500, qPrintable(QString("reconnect took %1 ms").arg(t.elapsed())));
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 2, 10000);
        QCOMPARE(cs.last().first().toBool(), true);
    }
    void staleWhileSocketOpen() {
        N2kClient c(path(), 200, 100);
        QSignalSpy vs(&c, &N2kClient::vessel), cs(&c, &N2kClient::connectionChanged);
        c.start();
        QVERIFY(accept());
        send(kHello + kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(vs.count(), 1, 10000);
        QTRY_COMPARE_WITH_TIMEOUT(cs.count(), 2, 10000);
        QCOMPARE(cs.last().first().toBool(), false);
        QCOMPARE(m_peer->state(), QLocalSocket::ConnectedState);
        // Data resumes on the same socket: live again.
        send(kVesselLine);
        QTRY_COMPARE_WITH_TIMEOUT(cs.count(), 3, 10000);
        QCOMPARE(cs.last().first().toBool(), true);
    }
    void modelsClearWhenNotLive() {
        VesselModel vm;
        AisModel am;
        VesselState s;
        s.depthM = 5.0;
        AisTarget t;
        t.mmsi = 7;
        vm.setLive(true);
        am.setLive(true);
        QSignalSpy ch(&vm, &VesselModel::changed);
        vm.setState(s);
        am.setTargets({t});
        QCOMPARE(ch.count(), 1);
        QVERIFY(vm.live());
        QCOMPARE(*vm.state().depthM, 5.0);
        QCOMPARE(am.rowCount(), 1);
        QCOMPARE(am.data(am.index(0), AisModel::MmsiRole).toUInt(), 7u);
        QCOMPARE(am.roleNames().value(AisModel::PosAgeRole), QByteArray("posAge"));
        vm.setLive(false);
        am.setLive(false);
        QVERIFY(!vm.state().depthM);
        QVERIFY(!vm.live());
        QCOMPARE(am.rowCount(), 0);
        QVERIFY(am.targets().isEmpty());
        QCOMPARE(ch.count(), 2);
    }
    // Contract: not live shows "--"; a late setState or setTargets must not repopulate the cleared models.
    void modelsIgnoreDataWhileNotLive() {
        VesselModel vm;
        AisModel am;
        VesselState s;
        s.depthM = 5.0;
        AisTarget t;
        t.mmsi = 7;
        QSignalSpy ch(&vm, &VesselModel::changed), rs(&am, &AisModel::modelReset);
        vm.setState(s);
        am.setTargets({t});
        QCOMPARE(ch.count(), 0);
        QVERIFY(!vm.state().depthM);
        QCOMPARE(rs.count(), 0);
        QCOMPARE(am.rowCount(), 0);
        vm.setLive(true);
        am.setLive(true);
        vm.setState(s);
        am.setTargets({t});
        QCOMPARE(*vm.state().depthM, 5.0);
        QCOMPARE(am.rowCount(), 1);
        vm.setLive(false);
        am.setLive(false);
        vm.setState(s);
        am.setTargets({t});
        QVERIFY(!vm.state().depthM);
        QCOMPARE(am.rowCount(), 0);
    }
};

QTEST_GUILESS_MAIN(TstN2kClient)
#include "tst_n2kclient.moc"
