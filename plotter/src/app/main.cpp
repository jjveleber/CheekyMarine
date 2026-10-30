#include "app/Icons.h"
#include "app/MapLibreChartMap.h"
#include "core/AisModel.h"
#include "core/AppInfo.h"
#include "core/ChartController.h"
#include "core/N2kClient.h"
#include "core/NumbersModel.h"
#include "core/PackCatalog.h"
#include "core/PaletteController.h"
#include "core/Recovery.h"
#include "core/Settings.h"
#include "core/Slots.h"
#include "core/Store.h"
#include "core/TouchLock.h"
#include "core/Tracks.h"
#include "core/Units.h"
#include "core/VesselModel.h"

#include <QCommandLineParser>
#include <QDateTime>
#include <QDebug>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QtQml/qqmlextensionplugin.h>
#include <QQuickView>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSGRendererInterface>
#include <QScreen>
#include <QStandardPaths>
#include <QTimer>
#include <chrono>
#include <memory>

Q_IMPORT_QML_PLUGIN(CheekyMarinePlugin)

namespace {

// Shows the recovery screen instead of the app until the store opens (returned) or the window is
// closed (null).
std::unique_ptr<Store> recover(QGuiApplication& app, const QString& dir, StoreError error, QSize size) {
    Recovery rec(dir, error);
    std::unique_ptr<Store> store;
    QQuickView view;
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setInitialProperties({{"recovery", QVariant::fromValue(static_cast<QObject*>(&rec))}});
    view.loadFromModule("CheekyMarine", "RecoveryScreen");
    if (view.status() != QQuickView::Ready) {
        qCritical() << "the recovery screen failed to load";
        return nullptr;
    }
    // Units follows the window here, as Main.qml makes it do in the app.
    auto* units = view.engine()->singletonInstance<QObject*>("CheekyMarine", "Units");
    const auto sizeUnits = [&view, units] {
        units->setProperty("windowWidth", view.width());
        units->setProperty("windowHeight", view.height());
    };
    QObject::connect(&view, &QWindow::widthChanged, units, sizeUnits);
    QObject::connect(&view, &QWindow::heightChanged, units, sizeUnits);
    view.resize(size.isValid() ? size : QSize(1024, 600));
    sizeUnits();
    QObject::connect(
        &rec, &Recovery::recovered, &app,
        [&] {
            store = rec.takeStore();
            qInfo() << "started fresh; the old file is" << rec.movedTo();
            QCoreApplication::exit(0);
        },
        Qt::QueuedConnection);
    view.show();
    app.exec();
    return store;
}

} // namespace

int main(int argc, char* argv[]) {
    // The MapLibre library is built with the OpenGL renderer only.
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationName(QStringLiteral("cheekyplotter"));

    const QString appData = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    QCommandLineParser cli;
    cli.addHelpOption();
    QCommandLineOption socketOpt("socket", "n2kd JSON socket.", "path", "/run/cheekymarine/n2k.sock");
    QCommandLineOption packsOpt("packs", "Directory of installed chart and bathy packs.", "dir", appData + "/packs");
    QCommandLineOption dataOpt("data", "Directory for plotter.db.", "dir", appData);
    QCommandLineOption windowOpt("window", "Window size, WxH (for example 1024x600).", "WxH");
    // Dev and checkpoint aids: save a window grab N ms after start. Repeatable; paired in order.
    QCommandLineOption shotOpt("screenshot", "Save a window grab to PATH.", "path");
    QCommandLineOption shotAfterOpt("screenshot-after-ms", "Delay for the matching --screenshot.", "ms");
    // Dev and checkpoint aids: write Settings::paletteMode / chartMode at start (they persist).
    QCommandLineOption paletteOpt("palette", "Set the palette mode: auto, day, dusk or night.", "mode");
    QCommandLineOption modeOpt("mode", "Set the chart mode: nav or fish.", "mode");
    // Dev and checkpoint aids: write the overlay slots at start (the defaults, or the defaults all
    // on; they persist) and choose the page shown first (not stored).
    QCommandLineOption slotsOpt("slots", "Set the overlay slots: default or all.", "set");
    QCommandLineOption pageOpt("page", "Page shown first: chart, numbers, tracks, settings or about.", "page");
    QCommandLineOption sheetOpt("sheet", "Open a sheet on the chart page: legend or ais.", "sheet");
    QCommandLineOption lockOpt("lock", "Start with the touch lock on.");
    QCommandLineOption recordOpt("record", "Turn track recording on at start (it persists).");
    for (QCommandLineOption* o : {&shotOpt, &shotAfterOpt, &paletteOpt, &modeOpt, &slotsOpt, &pageOpt, &sheetOpt, &lockOpt, &recordOpt})
        o->setFlags(QCommandLineOption::HiddenFromHelp);
    cli.addOptions(
        {socketOpt, packsOpt, dataOpt, windowOpt, shotOpt, shotAfterOpt, paletteOpt, modeOpt, slotsOpt, pageOpt, sheetOpt, lockOpt, recordOpt});
    cli.process(app);

    QSize windowSize;
    if (cli.isSet(windowOpt)) {
        const auto m = QRegularExpression("^(\\d+)x(\\d+)$").match(cli.value(windowOpt));
        if (!m.hasMatch()) {
            qCritical() << "--window wants WxH, got" << cli.value(windowOpt);
            return 2;
        }
        windowSize = QSize(m.captured(1).toInt(), m.captured(2).toInt());
    }
    const QStringList shots = cli.values(shotOpt), shotDelays = cli.values(shotAfterOpt);
    if (shots.size() != shotDelays.size()) {
        qCritical() << "each --screenshot needs a --screenshot-after-ms";
        return 2;
    }
    const QStringList paletteModes{"auto", "day", "dusk", "night"}, chartModes{"nav", "fish"};
    if (cli.isSet(paletteOpt) && !paletteModes.contains(cli.value(paletteOpt))) {
        qCritical() << "--palette wants auto, day, dusk or night, got" << cli.value(paletteOpt);
        return 2;
    }
    if (cli.isSet(modeOpt) && !chartModes.contains(cli.value(modeOpt))) {
        qCritical() << "--mode wants nav or fish, got" << cli.value(modeOpt);
        return 2;
    }
    if (cli.isSet(slotsOpt) && cli.value(slotsOpt) != "default" && cli.value(slotsOpt) != "all") {
        qCritical() << "--slots wants default or all, got" << cli.value(slotsOpt);
        return 2;
    }
    const QStringList pages{"chart", "numbers", "tracks", "settings", "about"};
    if (cli.isSet(pageOpt) && !pages.contains(cli.value(pageOpt))) {
        qCritical() << "--page wants one of" << pages << "got" << cli.value(pageOpt);
        return 2;
    }

    if (cli.isSet(sheetOpt) && cli.value(sheetOpt) != "legend" && cli.value(sheetOpt) != "ais") {
        qCritical() << "--sheet wants legend or ais, got" << cli.value(sheetOpt);
        return 2;
    }

    // Every open error shows the recovery screen. NewerMajor and Corrupt need a fresh file. Io may be
    // a file that is not ours or one SQLite reports as corrupt late (start fresh helps), or a passing
    // or permission problem (try again; a failed move aside is reported on the screen).
    std::unique_ptr<Store> store;
    if (auto opened = Store::open(cli.value(dataOpt))) {
        store = std::move(*opened);
    } else {
        qWarning() << "cannot open the store in" << cli.value(dataOpt) << storeErrorReason(opened.error());
        store = recover(app, cli.value(dataOpt), opened.error(), windowSize);
        if (!store) return 1;
    }
    Settings settings(*store);
    if (cli.isSet(paletteOpt)) settings.setPaletteMode(cli.value(paletteOpt));
    if (cli.isSet(modeOpt)) settings.setChartMode(cli.value(modeOpt));
    if (cli.isSet(recordOpt)) settings.setTrackRecording(true);

    VesselModel vessel;
    AisModel ais;
    N2kClient client(cli.value(socketOpt));
    // connectionChanged(true) comes before the data it unlocks; false clears both models.
    QObject::connect(&client, &N2kClient::connectionChanged, &vessel, &VesselModel::setLive);
    QObject::connect(&client, &N2kClient::connectionChanged, &ais, &AisModel::setLive);
    QObject::connect(&client, &N2kClient::vessel, &vessel, &VesselModel::setState);
    QObject::connect(&client, &N2kClient::ais, &ais, &AisModel::setTargets);

    // Recording follows the setting; the vessel feeds it. The timer writes a buffer a quiet data
    // feed would leave waiting. Declared before the engine and the chart so they go first.
    TrackStore trackStore(*store);
    TrackRecorder recorder(trackStore, settings, [] { // monotonic: the wall clock steps when GPS or NTP corrects it
                                 return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
                             });
    TracksController tracksController(trackStore, recorder);
    QObject::connect(&vessel, &VesselModel::changed, &recorder, [&] { recorder.onVessel(vessel.state()); });
    QTimer recorderTimer;
    recorderTimer.setInterval(5000);
    QObject::connect(&recorderTimer, &QTimer::timeout, &recorder, &TrackRecorder::tick);
    recorderTimer.start();

    SlotsModel slotsModel(settings, vessel);
    NumbersModel numbersModel(settings, vessel);
    if (cli.value(slotsOpt) == "default") slotsModel.setSlotConfigs(defaultSlots());
    if (cli.value(slotsOpt) == "all") {
        QList<SlotConfig> all = defaultSlots();
        for (SlotConfig& c : all) c.on = true;
        slotsModel.setSlotConfigs(all);
    }

    const QList<PackInfo> packs = PackCatalog::scan(cli.value(packsOpt));
    for (const PackInfo& p : packs)
        if (!p.refused.isEmpty()) qWarning() << "pack refused:" << p.dir << p.refused;
    AppInfo appInfo(packs);
    // The client emits the hello's version before a schema mismatch.
    QObject::connect(&client, &N2kClient::daemonVersion, &appInfo, &AppInfo::setDaemonVersion);
    QObject::connect(&client, &N2kClient::schemaMismatch, &appInfo, &AppInfo::setSchemaMismatch);

    // Created here, not in QML, so the controller can hold its ChartMap; ChartPage reparents it.
    // Declared before the engine so it is destroyed after it, once the scene graph has released its node.
    auto mapItem = std::make_unique<MapLibreChartMap>();
    QQmlEngine::setObjectOwnership(mapItem.get(), QQmlEngine::CppOwnership);
    ChartController chart(mapItem->port(), settings, vessel, ais, packs);
    mapItem->setZoomRange(chart.minZoom(), chart.maxZoom());
    // The active track always draws, the others when shown.
    const auto showTracks = [&] { chart.setTracks(tracksController.shown()); };
    QObject::connect(&tracksController, &TracksController::shownChanged, &chart, showTracks);
    showTracks();

    // --sheet ais: select the first AIS target that arrives (a dev aid, like the other hidden options).
    if (cli.value(sheetOpt) == "ais") {
        auto once = std::make_shared<QMetaObject::Connection>();
        *once = QObject::connect(&ais, &QAbstractItemModel::modelReset, &chart, [&chart, &ais, once] {
            if (ais.targets().isEmpty()) return;
            chart.selectMmsi(ais.targets().constFirst().mmsi);
            QObject::disconnect(*once);
        });
    }

    // Icons are sized like the QML Units: from the window size and the panel diagonal setting.
    QQuickWindow* window = nullptr;
    const auto iconPxPerMm = [&] {
        const QSize s = window ? window->size()
                               : windowSize.isValid() ? windowSize : QGuiApplication::primaryScreen()->size();
        return pxPerMm(s.width(), s.height(), settings.panelDiagonalIn());
    };

    // The palette drives the chart style, the icons and (in Main.qml) the Theme. Icons first, so the
    // style reload that setPalette starts re-adds them in the new colours.
    PaletteController palette(settings, vessel, [] { return QDateTime::currentDateTimeUtc(); });
    const auto applyPalette = [&] {
        chart.setImages(chartIcons(iconPxPerMm(), palette.palette()));
        chart.setPalette(palette.palette());
    };
    applyPalette();
    QObject::connect(&palette, &PaletteController::paletteChanged, &chart, applyPalette);

    // The lock follows the timeout setting live. poll() runs every 100 ms; the window filter below
    // reports touches as activity. The clock is monotonic: the wall clock steps when GPS or NTP corrects it.
    QElapsedTimer lockClock;
    lockClock.start();
    TouchLock touchLock([&lockClock] { return lockClock.elapsed(); });
    touchLock.setTimeoutS(settings.touchLockTimeoutS());
    QObject::connect(&settings, &Settings::touchLockTimeoutSChanged, &touchLock,
                     [&] { touchLock.setTimeoutS(settings.touchLockTimeoutS()); });
    QTimer lockTimer;
    lockTimer.setInterval(TouchLock::kPollMs);
    QObject::connect(&lockTimer, &QTimer::timeout, &touchLock, &TouchLock::poll);
    lockTimer.start();
    if (cli.isSet(lockOpt)) touchLock.lockNow();

    QQmlApplicationEngine engine;
    QObject::connect(
        &engine, &QQmlApplicationEngine::objectCreationFailed, &app,
        [] {
            qCritical() << "the main QML failed to load";
            QCoreApplication::exit(1);
        },
        Qt::QueuedConnection);
    engine.setInitialProperties({{"chart", QVariant::fromValue(&chart)},
                                 {"chartMap", QVariant::fromValue(static_cast<QQuickItem*>(mapItem.get()))},
                                 {"paletteController", QVariant::fromValue(&palette)},
                                 {"settings", QVariant::fromValue(&settings)},
                                 {"vessel", QVariant::fromValue(&vessel)},
                                 {"appInfo", QVariant::fromValue(&appInfo)},
                                 {"slotsModel", QVariant::fromValue(&slotsModel)},
                                 {"numbersModel", QVariant::fromValue(&numbersModel)},
                                 {"touchLock", QVariant::fromValue(&touchLock)},
                                 {"tracksController", QVariant::fromValue(&tracksController)},
                                 {"page", cli.isSet(pageOpt) ? cli.value(pageOpt) : QStringLiteral("chart")},
                                 {"legendOpen", cli.value(sheetOpt) == "legend"}});
    engine.loadFromModule("CheekyMarine", "Main");
    if (engine.rootObjects().isEmpty()) {
        qCritical() << "the main QML failed to load";
        return 1;
    }
    window = qobject_cast<QQuickWindow*>(engine.rootObjects().constFirst());
    if (!window) {
        qCritical() << "the main QML is not a window";
        return 1;
    }
    window->installEventFilter(new TouchActivityFilter(&touchLock, window));
    if (windowSize.isValid()) window->resize(windowSize);
    const auto resizeIcons = [&] { chart.setImages(chartIcons(iconPxPerMm(), palette.palette())); };
    resizeIcons();
    QObject::connect(window, &QWindow::widthChanged, &chart, resizeIcons);
    QObject::connect(window, &QWindow::heightChanged, &chart, resizeIcons);
    QObject::connect(&settings, &Settings::panelDiagonalInChanged, &chart, resizeIcons);

    for (qsizetype i = 0; i < shots.size(); ++i) {
        QTimer::singleShot(shotDelays[i].toInt(), window, [window, path = shots[i]] {
            const bool ok = window->grabWindow().save(path);
            qInfo() << "screenshot" << path << (ok ? "saved" : "FAILED");
        });
    }

    client.start();
    return app.exec();
}
