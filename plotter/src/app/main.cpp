#include "app/Icons.h"
#include "app/MapLibreChartMap.h"
#include "core/AisModel.h"
#include "core/ChartController.h"
#include "core/N2kClient.h"
#include "core/PackCatalog.h"
#include "core/PaletteController.h"
#include "core/Settings.h"
#include "core/Store.h"
#include "core/VesselModel.h"

#include <QCommandLineParser>
#include <QDebug>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QtQml/qqmlextensionplugin.h>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSGRendererInterface>
#include <QScreen>
#include <QStandardPaths>
#include <QTimer>
#include <memory>

Q_IMPORT_QML_PLUGIN(CheekyMarinePlugin)

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
    shotOpt.setFlags(QCommandLineOption::HiddenFromHelp);
    shotAfterOpt.setFlags(QCommandLineOption::HiddenFromHelp);
    paletteOpt.setFlags(QCommandLineOption::HiddenFromHelp);
    modeOpt.setFlags(QCommandLineOption::HiddenFromHelp);
    cli.addOptions({socketOpt, packsOpt, dataOpt, windowOpt, shotOpt, shotAfterOpt, paletteOpt, modeOpt});
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

    auto store = Store::open(cli.value(dataOpt));
    if (!store) { // Task 12 replaces this with the recovery screen.
        qCritical() << "cannot open the store in" << cli.value(dataOpt) << "error" << static_cast<int>(store.error());
        return 1;
    }
    Settings settings(**store);
    if (cli.isSet(paletteOpt)) settings.setPaletteMode(cli.value(paletteOpt));
    if (cli.isSet(modeOpt)) settings.setChartMode(cli.value(modeOpt));

    VesselModel vessel;
    AisModel ais;
    N2kClient client(cli.value(socketOpt));
    // connectionChanged(true) comes before the data it unlocks; false clears both models.
    QObject::connect(&client, &N2kClient::connectionChanged, &vessel, &VesselModel::setLive);
    QObject::connect(&client, &N2kClient::connectionChanged, &ais, &AisModel::setLive);
    QObject::connect(&client, &N2kClient::vessel, &vessel, &VesselModel::setState);
    QObject::connect(&client, &N2kClient::ais, &ais, &AisModel::setTargets);

    const QList<PackInfo> packs = PackCatalog::scan(cli.value(packsOpt));
    for (const PackInfo& p : packs)
        if (!p.refused.isEmpty()) qWarning() << "pack refused:" << p.dir << p.refused;

    // Created here, not in QML, so the controller can hold its ChartMap; ChartPage reparents it.
    // Declared before the engine so it is destroyed after it, once the scene graph has released its node.
    auto mapItem = std::make_unique<MapLibreChartMap>();
    QQmlEngine::setObjectOwnership(mapItem.get(), QQmlEngine::CppOwnership);
    ChartController chart(mapItem->port(), settings, vessel, ais, packs);
    // Temporary physical size from the screen; Task 12 switches to Units.
    const double pxPerMm = QGuiApplication::primaryScreen()->physicalDotsPerInch() / 25.4;
    mapItem->setZoomRange(chart.minZoom(), chart.maxZoom());

    // The palette drives the chart style, the icons and (in Main.qml) the Theme. Icons first, so the
    // style reload that setPalette starts re-adds them in the new colours.
    PaletteController palette(settings, vessel, [] { return QDateTime::currentDateTimeUtc(); });
    const auto applyPalette = [&] {
        chart.setImages(chartIcons(pxPerMm, palette.palette()));
        chart.setPalette(palette.palette());
    };
    applyPalette();
    QObject::connect(&palette, &PaletteController::paletteChanged, &chart, applyPalette);

    QQmlApplicationEngine engine;
    engine.setInitialProperties({{"chart", QVariant::fromValue(&chart)},
                                 {"chartMap", QVariant::fromValue(static_cast<QQuickItem*>(mapItem.get()))},
                                 {"paletteController", QVariant::fromValue(&palette)}});
    engine.loadFromModule("CheekyMarine", "Main");
    if (engine.rootObjects().isEmpty()) return 1;
    auto* window = qobject_cast<QQuickWindow*>(engine.rootObjects().constFirst());
    if (window && windowSize.isValid()) window->resize(windowSize);

    for (qsizetype i = 0; i < shots.size(); ++i) {
        QTimer::singleShot(shotDelays[i].toInt(), window, [window, path = shots[i]] {
            const bool ok = window->grabWindow().save(path);
            qInfo() << "screenshot" << path << (ok ? "saved" : "FAILED");
        });
    }

    client.start();
    return app.exec();
}
