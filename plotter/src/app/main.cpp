#include <QDebug>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QMapLibre/Utils>

int main(int argc, char* argv[]) {
    // The MapLibre library is built with the OpenGL renderer only.
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication app(argc, argv);
    // Touches a QMapLibre symbol so the link and RPATH to libQMapLibre.so are proven at start-up.
    qInfo() << "QMapLibre metres per pixel at z10, lat 48:" << QMapLibre::metersPerPixelAtLatitude(48.0, 10.0);
    QQmlApplicationEngine engine;
    engine.loadFromModule("CheekyMarine", "Main");
    return app.exec();
}
