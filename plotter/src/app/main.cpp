#include "app/Icons.h"
#include "app/LegendImageProvider.h"
#include "app/MapLibreChartMap.h"
#include "core/AisModel.h"
#include "core/AppInfo.h"
#include "core/ChartController.h"
#include "core/MonotonicClock.h"
#include "core/Geo.h"
#include "core/N2kClient.h"
#include "core/PackCatalog.h"
#include "core/PackMerge.h"
#include "core/PanPath.h"
#include "core/PaletteController.h"
#include "core/Recovery.h"
#include "core/Settings.h"
#include "core/SignalBridge.h"
#include "core/Store.h"
#include "core/TouchLock.h"
#include "core/Tracks.h"
#include "core/Units.h"
#include "core/VesselModel.h"
#include "core/ViewDraft.h"
#include "core/ViewsModel.h"
#include "core/WindowOptions.h"

#include <QCommandLineParser>
#include <QCoreApplication>
#include <QDateTime>
#include <QDebug>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QPointF>
#include <optional>
#include <QQmlApplicationEngine>
#include <QtQml/qqmlextensionplugin.h>
#include <QQuickView>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSGRendererInterface>
#include <QScreen>
#include <QStandardPaths>
#include <QTimer>
#include <csignal>
#include <cstdio>
#include <memory>
#include <utility>

Q_IMPORT_QML_PLUGIN(CheekyMarinePlugin)

namespace {

// Shows the recovery screen instead of the app until the store opens (returned) or the window is
// closed (null).
std::unique_ptr<Store> recover(QGuiApplication& app, const QString& dir, StoreError error, bool fullscreen, QSize size) {
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
    view.resize(QSize(1024, 600));
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
    applyWindowOptions(view, fullscreen, size);
    app.exec();
    return store;
}

} // namespace

// `cheekyplotter --merge-packs DIR`: merges the usable packs under DIR (newest per region) into
// DIR/merged and prints one line per written file. Runs without a display.
static int mergePacksCli(int argc, char* argv[], const QString& dir) {
    QCoreApplication app(argc, argv);
    const QList<PackInfo> all = PackCatalog::scan(dir);
    QList<PackInfo> use;
    QStringList written;
    for (const QString& kind : {QStringLiteral("charts"), QStringLiteral("bathy")}) {
        const QList<PackInfo> k = PackCatalog::usable(all, kind);
        use += k;
        if (k.size() >= 2)
            for (const QString& f : kind == QLatin1String("charts") ? kChartsFiles : kBathyFiles)
                written << dir + QStringLiteral("/merged/") + kind + QLatin1Char('/') + f;
    }
    const auto r = mergePacks(use, dir + QStringLiteral("/merged"));
    if (!r) {
        fprintf(stderr, "%s\n", qPrintable(r.error()));
        return 1;
    }
    for (const QString& f : written)
        printf("%s\n", qPrintable(f));
    return 0;
}

int main(int argc, char* argv[]) {
    for (int i = 1; i < argc; ++i) {
        const QString a = QString::fromLocal8Bit(argv[i]);
        if (a == QLatin1String("--merge-packs") && i + 1 < argc)
            return mergePacksCli(argc, argv, QString::fromLocal8Bit(argv[i + 1]));
        if (a.startsWith(QLatin1String("--merge-packs=")))
            return mergePacksCli(argc, argv, a.mid(14));
    }
    QElapsedTimer startTimer;
    startTimer.start();
    // The MapLibre library is built with the OpenGL renderer only.
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication app(argc, argv);
    if (const QString problem = platformProblem(QGuiApplication::platformName()); !problem.isEmpty()) {
        qCritical().noquote() << problem;
        return 1;
    }
    QGuiApplication::setApplicationName(QStringLiteral("cheekyplotter"));

    const QString appData = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    QCommandLineParser cli;
    cli.addHelpOption();
    QCommandLineOption socketOpt("socket", "n2kd JSON socket.", "path", "/run/cheekymarine/n2k.sock");
    QCommandLineOption packsOpt("packs", "Directory of installed chart and bathy packs (default <data dir>/packs).", "dir");
    QCommandLineOption dataOpt("data", "Directory for plotter.db.", "dir", appData);
    QCommandLineOption windowOpt("window", "Window size, WxH (for example 1024x600), ignored with --fullscreen.", "WxH");
    QCommandLineOption fullscreenOpt("fullscreen", "Show the window full screen (--window is ignored).");
    // Dev and checkpoint aids: save a window grab N ms after start. Repeatable; paired in order.
    QCommandLineOption shotOpt("screenshot", "Save a window grab to PATH.", "path");
    QCommandLineOption shotAfterOpt("screenshot-after-ms", "Delay for the matching --screenshot.", "ms");
    // Dev and checkpoint aids: write Settings::paletteMode at start (it persists); choose the view
    // (it persists, as a tab tap does) and the page shown first (not stored); quit after a delay.
    QCommandLineOption paletteOpt("palette", "Set the palette mode: auto, day, dusk or night.", "mode");
    QCommandLineOption viewOpt("view", "View shown first, by its short name.", "short");
    QCommandLineOption pageOpt("page", "Page shown first: home, view, tracks, settings or about.", "page");
    QCommandLineOption editorOpt("editor", "Open the view editor on the shown view.");
    QCommandLineOption sheetOpt("sheet", "Open a sheet: legend, ais, setup, slot, cell, gallery or keyboard.", "sheet");
    QCommandLineOption lockOpt("lock", "Start with the touch lock on.");
    QCommandLineOption recordOpt("record", "Turn track recording on at start (it persists).");
    QCommandLineOption exitAfterOpt("exit-after-ms", "Quit N ms after start.", "ms");
    QCommandLineOption frameStatsOpt("frame-stats", "Print the frame interval and track write summaries at quit.");
    QCommandLineOption seedTrackOpt("seed-track", "Prepend N synthetic points to every active-track write (for the frame measurement).", "n");
    QCommandLineOption panPathOpt("pan-path", "Pan the chart through LAT,LON,ZOOM;LAT,LON,ZOOM;... again and again (follow off).", "path");
    QCommandLineOption panLegOpt("pan-leg-ms", "Time for each --pan-path leg (default 1500).", "ms");
    QCommandLineOption positionOpt("position", "Chart center while there is no vessel position.", "lat,lon");
    for (QCommandLineOption* o : {&positionOpt, &shotOpt, &shotAfterOpt, &paletteOpt, &viewOpt, &pageOpt, &editorOpt, &sheetOpt,
                                  &lockOpt, &recordOpt, &exitAfterOpt, &frameStatsOpt, &seedTrackOpt, &panPathOpt, &panLegOpt})
        o->setFlags(QCommandLineOption::HiddenFromHelp);
    cli.addOptions({positionOpt, socketOpt, packsOpt, dataOpt, windowOpt, fullscreenOpt, shotOpt, shotAfterOpt, paletteOpt, viewOpt, pageOpt,
                    editorOpt, sheetOpt, lockOpt, recordOpt, exitAfterOpt, frameStatsOpt, seedTrackOpt, panPathOpt, panLegOpt});
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
    std::optional<QPointF> startPosition;
    if (cli.isSet(positionOpt)) {
        const auto m = QRegularExpression("^(-?\\d+(\\.\\d+)?),(-?\\d+(\\.\\d+)?)$").match(cli.value(positionOpt));
        if (!m.hasMatch()) {
            qCritical() << "--position wants LAT,LON, got" << cli.value(positionOpt);
            return 2;
        }
        startPosition = QPointF(m.captured(1).toDouble(), m.captured(3).toDouble());
    }
    const QStringList shots = cli.values(shotOpt), shotDelays = cli.values(shotAfterOpt);
    if (shots.size() != shotDelays.size()) {
        qCritical() << "each --screenshot needs a --screenshot-after-ms";
        return 2;
    }
    const QStringList paletteModes{"auto", "day", "dusk", "night"};
    if (cli.isSet(paletteOpt) && !paletteModes.contains(cli.value(paletteOpt))) {
        qCritical() << "--palette wants auto, day, dusk or night, got" << cli.value(paletteOpt);
        return 2;
    }
    const QStringList pages{"home", "view", "tracks", "settings", "about"};
    if (cli.isSet(pageOpt) && !pages.contains(cli.value(pageOpt))) {
        qCritical() << "--page wants one of" << pages << "got" << cli.value(pageOpt);
        return 2;
    }

    // setup, slot (TL), cell (the first cell, on a view with no chart), gallery and keyboard (the
    // Setup Name field) are editor sheets: they open the editor too.
    const QStringList sheets{"legend", "ais", "setup", "slot", "cell", "gallery", "keyboard"};
    if (cli.isSet(sheetOpt) && !sheets.contains(cli.value(sheetOpt))) {
        qCritical() << "--sheet wants one of" << sheets << "got" << cli.value(sheetOpt);
        return 2;
    }
    const QStringList editorSheets{"setup", "slot", "cell", "gallery", "keyboard"};
    const bool editorOpen = cli.isSet(editorOpt) || editorSheets.contains(cli.value(sheetOpt));
    bool exitAfterOk = true;
    const int exitAfterMs = cli.value(exitAfterOpt).toInt(&exitAfterOk);
    if (cli.isSet(exitAfterOpt) && (!exitAfterOk || exitAfterMs < 0)) {
        qCritical() << "--exit-after-ms wants a whole number of ms, got" << cli.value(exitAfterOpt);
        return 2;
    }
    QList<PanPoint> panPath;
    if (cli.isSet(panPathOpt)) {
        auto parsed = parsePanPath(cli.value(panPathOpt));
        if (!parsed) {
            qCritical().noquote() << "--pan-path:" << parsed.error();
            return 2;
        }
        panPath = *parsed;
    }
    bool panLegOk = true;
    const int panLegMs = cli.isSet(panLegOpt) ? cli.value(panLegOpt).toInt(&panLegOk) : 1500;
    if (cli.isSet(panLegOpt) && (!panLegOk || panLegMs <= 0)) {
        qCritical() << "--pan-leg-ms wants a whole number of ms above 0, got" << cli.value(panLegOpt);
        return 2;
    }
    bool seedOk = true;
    const int seedN = cli.value(seedTrackOpt).toInt(&seedOk);
    if (cli.isSet(seedTrackOpt) && (!seedOk || seedN < 0 || seedN > 1000000)) {
        qCritical() << "--seed-track wants a whole number up to 1000000, got" << cli.value(seedTrackOpt);
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
        store = recover(app, cli.value(dataOpt), opened.error(), cli.isSet(fullscreenOpt), windowSize);
        if (!store) return 1;
    }
    Settings settings(*store);
    if (cli.isSet(paletteOpt)) settings.setPaletteMode(cli.value(paletteOpt));
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
    TrackRecorder recorder(trackStore, settings, boottimeSecondsClock()); // the wall clock steps when GPS or NTP corrects it; a suspend counts
    TracksController tracksController(trackStore, recorder);
    QObject::connect(&vessel, &VesselModel::changed, &recorder, [&] { recorder.onVessel(vessel.state()); });
    QTimer recorderTimer;
    recorderTimer.setInterval(5000);
    QObject::connect(&recorderTimer, &QTimer::timeout, &recorder, &TrackRecorder::tick);
    recorderTimer.start();
    // Ctrl-C, SIGTERM (systemctl stop) and SIGHUP (a closed terminal) leave app.exec(), so the
    // recorder destructor writes buffered points.
    SignalBridge signalBridge{SIGINT, SIGTERM, SIGHUP};
    QObject::connect(&signalBridge, &SignalBridge::signaled, &app, [](int) { QCoreApplication::quit(); });

    // The saved views and the draft of the shown one (Main.qml loads the current view into it).
    ViewsModel views(*store, settings, [] { return QDateTime::currentSecsSinceEpoch(); });
    ViewDraft draft(vessel, settings);
    if (cli.isSet(viewOpt)) {
        const QString id = views.idOfShort(cli.value(viewOpt));
        if (id.isEmpty()) {
            QStringList shorts;
            for (const View& v : views.views()) shorts << v.shortName;
            qCritical() << "--view wants the short name of a view, one of" << shorts << "got" << cli.value(viewOpt);
            return 2;
        }
        views.setCurrentId(id);
    }
    // The cell sheet and the layout gallery belong to a view with no chart (R85).
    if (const QString s = cli.value(sheetOpt); s == "cell" || s == "gallery") {
        const auto shown = views.view(views.currentId());
        if (!shown || shown->chart != ViewChart::None) {
            qCritical().noquote() << "--sheet" << s << "needs a None view (for example --view \"Big #\")";
            return 2;
        }
    }

    const QString packsDir = cli.isSet(packsOpt) ? cli.value(packsOpt) : cli.value(dataOpt) + "/packs";
    const QList<PackInfo> packs = PackCatalog::scan(packsDir);

    // Created here, not in QML, so the controller can hold its ChartMap; ChartPage reparents it.
    // Declared before the engine so it is destroyed after it, once the scene graph has released its node.
    auto mapItem = std::make_unique<MapLibreChartMap>();
    QQmlEngine::setObjectOwnership(mapItem.get(), QQmlEngine::CppOwnership);
    ChartController chart(mapItem->port(), settings, vessel, ais, packs, packsDir);
    if (startPosition) chart.setStartPosition(startPosition->x(), startPosition->y());
    mapItem->setZoomRange(chart.minZoom(), chart.maxZoom());
    // The controller adds its own refusals (a style it cannot use) to the scan's.
    for (const PackInfo& p : chart.packs())
        if (!p.refused.isEmpty()) qWarning() << "pack refused:" << p.dir << p.refused;
    // sets/<v>/plotter/bin/ up two: the lock of the set this binary belongs to.
    AppInfo appInfo(chart.packs(), chart.packsInUse(), readSetVersion(QCoreApplication::applicationDirPath() + "/../../cheekymarine.lock"),
                    chart.packNotices(), chart.packModes());
    connectAppInfo(client, appInfo);
    // The active track always draws, the finished ones when shown.
    if (cli.isSet(seedTrackOpt)) chart.setSeedTrack(syntheticTrack(seedN));
    bindTracks(chart, tracksController);

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

    // The lock locks only from its button (or --lock). poll() runs every 100 ms while it is on, for
    // the unlock hold. The clock is monotonic: the wall clock steps when GPS or NTP corrects it.
    TouchLock touchLock(monotonicMsClock());
    QTimer lockTimer;
    pollWhileNeeded(touchLock, lockTimer);
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
                                 {"views", QVariant::fromValue(&views)},
                                 {"draft", QVariant::fromValue(&draft)},
                                 {"touchLock", QVariant::fromValue(&touchLock)},
                                 {"tracksController", QVariant::fromValue(&tracksController)},
                                 {"page", cli.isSet(pageOpt) ? cli.value(pageOpt) : QStringLiteral("view")},
                                 {"legendOpen", cli.value(sheetOpt) == "legend"},
                                 {"editorOpen", editorOpen},
                                 {"sheet", cli.value(sheetOpt)}});
    // The legend's symbols: the shown style's sprite sheet and the chart icons. Both are read per
    // request, and the palette is in each overlay id, so a palette change needs no refresh here.
    engine.addImageProvider(QStringLiteral("legend"),
                            new LegendImageProvider([&chart] { return chart.spriteBase(); }, iconPxPerMm)); // the engine owns it
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
    applyWindowOptions(*window, cli.isSet(fullscreenOpt), windowSize);
    // The start time, logged once at the first frame. Frames can queue up before the disconnect
    // lands, so a flag keeps it to one line.
    auto readyConn = std::make_shared<QMetaObject::Connection>();
    auto readyLogged = std::make_shared<bool>(false);
    *readyConn = QObject::connect(window, &QQuickWindow::frameSwapped, window, [&startTimer, readyConn, readyLogged] {
        QObject::disconnect(*readyConn);
        if (std::exchange(*readyLogged, true)) return;
        qInfo().noquote() << QStringLiteral("ready in %1 ms").arg(startTimer.elapsed());
    });
    if (cli.isSet(frameStatsOpt)) {
        // Intervals between consecutive frames (the first frame has no predecessor), printed at quit.
        auto intervals = std::make_shared<QList<qint64>>();
        auto frameTimer = std::make_shared<QElapsedTimer>();
        QObject::connect(window, &QQuickWindow::frameSwapped, window, [intervals, frameTimer] {
            if (frameTimer->isValid()) intervals->append(frameTimer->restart());
            else frameTimer->start();
        });
        // And the main-thread time inside each active-track write, to tell a write stall from an idle gap.
        chart.setWriteTiming(true);
        QObject::connect(&app, &QCoreApplication::aboutToQuit, &app, [intervals, &chart] {
            qInfo().noquote() << frameStatsLine(*intervals);
            qInfo().noquote() << writeStatsLine(chart.writeTimesUs());
        });
    }
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

    if (!panPath.isEmpty()) {
        // Same camera path every run: every 16 ms follow is forced off and the center and zoom move.
        auto panClock = std::make_shared<QElapsedTimer>();
        panClock->start();
        auto* panTimer = new QTimer(&app);
        QObject::connect(panTimer, &QTimer::timeout, &app, [panClock, panPath, panLegMs, port = &mapItem->port(), &chart] {
            chart.setFollow(false); // a no-op while off; the recenter button can turn it back on
            const PanPoint p = panAt(panPath, panLegMs, panClock->elapsed());
            port->setCamera(p.lat, p.lon, p.zoom, 0);
        });
        panTimer->start(16);
    }

    if (cli.isSet(exitAfterOpt)) QTimer::singleShot(exitAfterMs, &app, &QCoreApplication::quit);

    client.start();
    return app.exec();
}
