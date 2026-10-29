// Throwaway MapLibre spike (plan 3, Task 1). Answers the six spike questions.
// Usage: mlnspike [--mode nav|fish|bathy] [--palette day|dusk|night]
//                 [--tiles mbtiles|<other form, see rewrite()>]
//                 [--test none|q3|q4|bench|reload] [--shot FILE.png] [--quit]
#include "mapitem.h"

#include <QCommandLineParser>
#include <QElapsedTimer>
#include <QFile>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QPainterPath>
#include <QQuickWindow>
#include <QTimer>
#include <algorithm>
#include <cmath>
#include <vector>

extern std::vector<double> g_renderMs;

namespace {

QString renderStats() {
    std::vector<double> v = g_renderMs;
    if (v.empty()) return "no frames";
    std::sort(v.begin(), v.end());
    double sum = 0;
    for (double x : v) sum += x;
    return QString("map render+glFinish ms: mean %1 p50 %2 p95 %3 max %4 (n=%5)")
        .arg(sum / v.size(), 0, 'f', 2)
        .arg(v[v.size() / 2], 0, 'f', 2)
        .arg(v[v.size() * 95 / 100], 0, 'f', 2)
        .arg(v.back(), 0, 'f', 2)
        .arg(v.size());
}

const QString kCharts =
    QStringLiteral("/home/jjveleber/projects/CheekyMarine/chartpack/work/charts/charts-puget-north-1.0.0");
const QString kBathy =
    QStringLiteral("/home/jjveleber/projects/CheekyMarine/chartpack/work/bathy/bathy-puget-north-1.0.0");

QString tileUrl(const QString& form, const QString& absPath) {
    if (form == "mbtiles") return "mbtiles://" + absPath; // mbtiles:///abs/path
    if (form == "mbtiles-rel") return "mbtiles://" + absPath.mid(1); // no leading slash
    qFatal("unknown --tiles form %s", qPrintable(form));
}

// The three pack contract rewrites, by hand.
QByteArray rewrite(const QString& mode, const QString& palette, const QString& tiles) {
    const QString packDir = mode == "nav" ? kCharts : kBathy;
    QFile f(packDir + "/styles/" + mode + "-" + palette + ".json");
    if (!f.open(QIODevice::ReadOnly)) qFatal("cannot open %s", qPrintable(f.fileName()));
    QJsonObject style = QJsonDocument::fromJson(f.readAll()).object();
    QJsonObject sources = style["sources"].toObject();
    for (auto it = sources.begin(); it != sources.end(); ++it) {
        QJsonObject src = it.value().toObject();
        const QString name = it.key();
        const QString file = (name == "enc" ? kCharts : kBathy) + "/" + name + ".mbtiles";
        src["url"] = tileUrl(tiles, file);
        it.value() = src;
    }
    style["sources"] = sources;
    const QString spriteName = style["sprite"].toString().section('/', -1);
    style["sprite"] = "file://" + packDir + "/sprites/" + spriteName;
    style["glyphs"] = "file://" + packDir + "/glyphs/{fontstack}/{range}.pbf";
    qInfo().noquote() << "sources" << QJsonDocument(sources).toJson(QJsonDocument::Compact);
    qInfo().noquote() << "sprite" << style["sprite"].toString() << "glyphs" << style["glyphs"].toString();
    return QJsonDocument(style).toJson(QJsonDocument::Compact);
}

QImage boatImage() {
    QImage img(48, 48, QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing);
    QPainterPath path;
    path.moveTo(24, 2);
    path.lineTo(40, 44);
    path.lineTo(24, 36);
    path.lineTo(8, 44);
    path.closeSubpath();
    p.setPen(QPen(Qt::black, 3));
    p.setBrush(QColor(255, 210, 0));
    p.drawPath(path);
    return img;
}

QByteArray boatGeoJson(double lat, double lon, double rot) {
    QJsonObject geom{{"type", "Point"}, {"coordinates", QJsonArray{lon, lat}}};
    QJsonObject feat{{"type", "Feature"}, {"geometry", geom}, {"properties", QJsonObject{{"rot", rot}}}};
    QJsonObject fc{{"type", "FeatureCollection"}, {"features", QJsonArray{feat}}};
    return QJsonDocument(fc).toJson(QJsonDocument::Compact);
}

} // namespace

int main(int argc, char** argv) {
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication app(argc, argv);

    QCommandLineParser cli;
    cli.addOptions({{"mode", "nav|fish", "mode", "nav"},
                    {"palette", "day|dusk|night", "palette", "day"},
                    {"tiles", "tile url form", "form", "mbtiles"},
                    {"test", "none|q3|q4|bench|reload", "test", "none"},
                    {"shot", "screenshot file", "file"},
                    {"quit", "quit after the test"}});
    cli.process(app);
    // "bathy" is accepted as an alias of the fishing mode name.
    const QString mode = cli.value("mode") == "bathy" ? QStringLiteral("fish") : cli.value("mode");
    const QString test = cli.value("test");
    const QString shot = cli.value("shot");

    QQuickWindow window;
    window.resize(1024, 600);
    window.setMinimumSize({1024, 600});
    window.setMaximumSize({1024, 600});
    auto* item = new MapItem(window.contentItem());
    item->setSize({1024, 600});
    window.show();

    QMapLibre::Map* map = item->map();

    int frames = 0;
    QObject::connect(&window, &QQuickWindow::frameSwapped, [&] { ++frames; });

    auto save = [&](const QString& file) {
        const QImage img = window.grabWindow();
        qInfo() << "screenshot" << file << img.size() << img.save(file);
    };
    auto quit = [&] {
        if (cli.isSet("quit")) QTimer::singleShot(200, &app, &QCoreApplication::quit);
    };

    // Q4 state
    double boatLat = 47.98, boatLon = -122.23, boatRot = 0;
    int geojsonUpdates = 0;
    QTimer boatTimer;
    boatTimer.setInterval(500); // 2 Hz
    bool skipImage = false; // reload-noimage: does a runtime image survive a style reload?
    auto addRuntimeOverlay = [&] {
        if (!skipImage) map->addImage("cm-boat", boatImage());
        map->addSource("cm-own", QVariantMap{{"type", "geojson"}, {"data", boatGeoJson(boatLat, boatLon, boatRot)}});
        // Layer params built from JSON, the way the app's addLayer(QJsonObject) would.
        const QJsonObject layer = QJsonDocument::fromJson(R"({
            "type": "symbol", "source": "cm-own",
            "layout": {"icon-image": "cm-boat", "icon-rotate": ["get", "rot"],
                       "icon-rotation-alignment": "map", "icon-allow-overlap": true,
                       "icon-ignore-placement": true}})")
                                      .object();
        map->addLayer("cm-own-boat", layer.toVariantMap());
        qInfo() << "runtime overlay added: source" << map->sourceExists("cm-own") << "layer"
                << map->layerExists("cm-own-boat");
    };
    QObject::connect(&boatTimer, &QTimer::timeout, [&] {
        boatLat += 0.0004;
        boatLon += 0.0006;
        boatRot = std::fmod(boatRot + 15, 360);
        map->updateSource("cm-own", QVariantMap{{"data", boatGeoJson(boatLat, boatLon, boatRot)}});
        ++geojsonUpdates;
    });

    bool styleLoadedOnce = false;
    bool fullyRenderedOnce = false;
    int styleLoads = 0;
    QObject::connect(item, &MapItem::mapChanged, [&](QMapLibre::Map::MapChange change) {
        if (change == QMapLibre::Map::MapChangeDidFinishLoadingStyle) {
            ++styleLoads;
            qInfo() << "style loaded #" << styleLoads << "(synchronous inside setStyleJson until 'setStyleJson returned')" << "layers" << map->layerIds().size();
            if ((test == "reload" || test == "reload-noimage") && styleLoads == 2) {
                skipImage = test == "reload-noimage";
                qInfo() << "after palette reload: cm-own source" << map->sourceExists("cm-own") << "layer"
                        << map->layerExists("cm-own-boat");
                addRuntimeOverlay();
                QTimer::singleShot(3000, [&] {
                    if (!shot.isEmpty()) save(shot);
                    quit();
                });
            }
            if (styleLoadedOnce) return;
            styleLoadedOnce = true;
            if (test == "q4" || test.startsWith("reload")) {
                addRuntimeOverlay();
                boatTimer.start();
            }
        }
        if (change == QMapLibre::Map::MapChangeDidFinishRenderingMapFullyRendered && !fullyRenderedOnce) {
            fullyRenderedOnce = true;
            qInfo() << "fully rendered";
            if (test == "none") {
                QTimer::singleShot(1000, [&] {
                    if (!shot.isEmpty()) save(shot);
                    quit();
                });
            } else if (test == "q3") {
                QTimer::singleShot(1000, [&] {
                    save(shot + ".before.png");
                    qInfo() << "filter before" << map->getFilter("depare-medium");
                    const QJsonArray filter =
                        QJsonDocument::fromJson(R"([">=", ["to-number", ["get","DRVAL1"]], 20])").array();
                    map->setFilter("depare-medium", filter.toVariantList());
                    qInfo() << "filter after" << map->getFilter("depare-medium");
                    QTimer::singleShot(3000, [&] {
                        save(shot);
                        quit();
                    });
                });
            } else if (test == "q4") {
                QTimer::singleShot(10000, [&] {
                    qInfo() << "geojson updates in 10 s window" << geojsonUpdates;
                    save(shot);
                    quit();
                });
            } else if (test.startsWith("reload")) {
                QTimer::singleShot(2000, [&] {
                    qInfo() << "before palette reload: cm-own source" << map->sourceExists("cm-own");
                    boatTimer.stop();
                    map->setStyleJson(QString::fromUtf8(rewrite(mode, "night", cli.value("tiles"))));
                });
            } else if (test == "bench") {
                QTimer::singleShot(1000, [&] {
                    auto* step = new QTimer(&app);
                    auto* clock = new QElapsedTimer;
                    clock->start();
                    frames = 0;
                    g_renderMs.clear();
                    static int phase = 0; // 0 pan, 1 zoom
                    static int ticks = 0;
                    step->setInterval(16);
                    QObject::connect(step, &QTimer::timeout, [&, step, clock] {
                        ++ticks;
                        if (phase == 0) {
                            const double a = ticks * 0.02;
                            map->moveBy(QPointF(8 * std::cos(a), 8 * std::sin(a)));
                        } else {
                            // zoom 13 -> ~15 -> 13 -> ~11 ... about the window centre
                            map->scaleBy(std::pow(2.0, 0.02 * std::sin(ticks * 0.02)), QPointF(512, 300));
                        }
                        item->update();
                        if (clock->elapsed() >= 10000) {
                            const double fps = frames * 1000.0 / clock->elapsed();
                            qInfo().noquote() << QString("BENCH mode=%1 %2: %3 frames in %4 ms = %5 fps")
                                                     .arg(mode, phase == 0 ? "pan" : "zoom")
                                                     .arg(frames)
                                                     .arg(clock->elapsed())
                                                     .arg(fps, 0, 'f', 1)
                                              << renderStats();
                            g_renderMs.clear();
                            if (phase == 0) {
                                phase = 1;
                                ticks = 0;
                                frames = 0;
                                clock->restart();
                            } else {
                                step->stop();
                                if (!shot.isEmpty()) save(shot);
                                quit();
                            }
                        }
                    });
                    step->start();
                });
            }
        }
    });

    // Load only after every mapChanged handler is connected: setStyleJson()
    // emits MapChangeDidFinishLoadingStyle synchronously, inside the call.
    map->setStyleJson(QString::fromUtf8(rewrite(mode, cli.value("palette"), cli.value("tiles"))));
    qInfo() << "setStyleJson returned";
    map->setCoordinateZoom({47.98, -122.23}, 13);

    return app.exec();
}
