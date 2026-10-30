// QuickTest runner for every tests/qml/tst_*.qml. The CheekyMarine QML module is linked in statically.
// The `fixture` context property gives the tests real models over a throw-away database.
#include "core/AppInfo.h"
#include "core/NumbersModel.h"
#include "core/Recovery.h"
#include "core/Settings.h"
#include "core/Slots.h"
#include "core/Store.h"
#include "core/TouchLock.h"
#include "core/Tracks.h"
#include "core/VesselModel.h"
#include <QDateTime>
#include <QQmlContext>
#include <QQmlEngine>
#include <QTemporaryDir>
#include <QtQml/qqmlextensionplugin.h>
#include <QtQuickTest>
#include <memory>

Q_IMPORT_QML_PLUGIN(CheekyMarinePlugin)

class Fixture : public QObject {
    Q_OBJECT
    Q_PROPERTY(QObject* settings READ settings CONSTANT)
    Q_PROPERTY(QObject* vessel READ vessel CONSTANT)
    Q_PROPERTY(QObject* slotsModel READ slotsModel CONSTANT)
    Q_PROPERTY(QObject* numbersModel READ numbersModel CONSTANT)
    Q_PROPERTY(QObject* appInfo READ appInfo CONSTANT)
    Q_PROPERTY(QObject* recovery READ recovery CONSTANT)
    Q_PROPERTY(QObject* touchLock READ touchLock CONSTANT)
    Q_PROPERTY(QObject* tracksController READ tracksController CONSTANT)

public:
    QObject* settings() const { return m_settings.get(); }
    QObject* vessel() { return &m_vessel; }
    QObject* slotsModel() const { return m_slots.get(); }
    QObject* numbersModel() const { return m_numbers.get(); }
    QObject* appInfo() const { return m_appInfo.get(); }
    QObject* recovery() const { return m_recovery.get(); }
    QObject* touchLock() { return &m_lock; }
    QObject* tracksController() const { return m_tracksController.get(); }

    // Default settings, no data, no daemon state.
    Q_INVOKABLE void reset() {
        m_settings->setSlotsJson(QJsonArray());
        m_settings->setBigNumbers({"depth", "sog"});
        m_settings->setPaletteMode("auto");
        m_settings->setDepthUnit("ft");
        m_settings->setDepths(1.8288, 3.048, 9.144);
        m_settings->setPanelDiagonalIn(10.1);
        m_settings->setOrientation("head");
        m_settings->setTrackRecording(false);
        for (const TrackInfo& t : m_trackStore->list()) m_trackStore->remove(t.id);
        m_tracksController->refresh();
        m_lock.setTimeoutS(0);
        m_lock.holdEnd();
        if (m_lock.locked()) { // unlock the way the user does
            m_lock.holdStart();
            advance(TouchLock::kHoldMs);
        }
        m_vessel.setLive(false);
        m_appInfo->setDaemonVersion(QString());
    }
    // A stored track of two points about 1.1 km apart, ten minutes long; returns its id.
    Q_INVOKABLE qint64 addTrack(double started) {
        const qint64 id = m_trackStore->create(started);
        TrackPoint a, b;
        a.t = started; a.lat = 47.98; a.lon = -122.23;
        b.t = started + 600; b.lat = 47.99; b.lon = -122.23;
        m_trackStore->append(id, {a, b});
        m_tracksController->refresh();
        return id;
    }
    // Moves the lock's clock on and polls it, as the 100 ms timer does.
    Q_INVOKABLE void advance(int ms) {
        m_nowMs += ms;
        m_lock.poll();
    }
    // Live data with the given depth (metres) and SOG (m/s); other fields absent.
    Q_INVOKABLE void setVessel(double depthM, double sogMs) {
        VesselState s;
        s.t = 1;
        s.depthM = depthM;
        s.sogMs = sogMs;
        m_vessel.setLive(true);
        m_vessel.setState(s);
    }

public slots:
    // The setup object exists before the application: the database is opened here.
    void applicationAvailable() {
        auto s = Store::open(m_dir.path());
        if (!s) qFatal("fixture: cannot open the store");
        m_store = std::move(*s);
        m_settings = std::make_unique<Settings>(*m_store);
        m_slots = std::make_unique<SlotsModel>(*m_settings, m_vessel);
        m_numbers = std::make_unique<NumbersModel>(*m_settings, m_vessel);
        m_trackStore = std::make_unique<TrackStore>(*m_store);
        m_recorder = std::make_unique<TrackRecorder>(*m_trackStore, *m_settings, [] { return QDateTime::currentSecsSinceEpoch() * 1.0; });
        m_tracksController = std::make_unique<TracksController>(*m_trackStore, *m_recorder);
        PackInfo charts;
        charts.kind = "charts";
        charts.region = "puget-north";
        charts.version = QVersionNumber(1, 0, 0);
        charts.dir = "/packs/charts-puget-north-1.0.0";
        charts.notice = "NOAA ENC data. Not certified for navigation.";
        PackInfo refused = charts;
        refused.version = QVersionNumber(2, 0, 0);
        refused.dir = "/packs/charts-puget-north-2.0.0";
        refused.refused = "schema 2 not supported";
        m_appInfo = std::make_unique<AppInfo>(QList<PackInfo>{charts, refused});
        m_recovery = std::make_unique<Recovery>(m_dir.filePath("broken"), StoreError::Io);
    }

    void qmlEngineAvailable(QQmlEngine* engine) { engine->rootContext()->setContextProperty("fixture", this); }

    // Before the application goes: the store needs it to close.
    void cleanupTestCase() {
        m_recovery.reset();
        m_tracksController.reset();
        m_recorder.reset();
        m_trackStore.reset();
        m_appInfo.reset();
        m_numbers.reset();
        m_slots.reset();
        m_settings.reset();
        m_store.reset();
    }

private:
    QTemporaryDir m_dir;
    std::unique_ptr<Store> m_store;
    std::unique_ptr<Settings> m_settings;
    VesselModel m_vessel;
    qint64 m_nowMs = 1000000;
    TouchLock m_lock{[this] { return m_nowMs; }};
    std::unique_ptr<SlotsModel> m_slots;
    std::unique_ptr<NumbersModel> m_numbers;
    std::unique_ptr<TrackStore> m_trackStore;
    std::unique_ptr<TrackRecorder> m_recorder;
    std::unique_ptr<TracksController> m_tracksController;
    std::unique_ptr<AppInfo> m_appInfo;
    std::unique_ptr<Recovery> m_recovery;
};

QUICK_TEST_MAIN_WITH_SETUP(cheekymarine_qml, Fixture)
#include "tst_qml.moc"
