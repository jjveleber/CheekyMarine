#include <QtTest>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>

#include "app/Icons.h"
#include "app/LegendImageProvider.h"

namespace {
void writeJson(const QString& path, const QJsonObject& o) {
    QFile f(path);
    QVERIFY(f.open(QIODevice::WriteOnly));
    f.write(QJsonDocument(o).toJson());
}
// A sheet at `stem` (base, or base + "@2x") with a solid red entry "red" of w x h and an SDF square
// "sdf" of w x w beside it.
void writeSheet(const QString& stem, int w, int h) {
    QImage img(2 * w, h, QImage::Format_ARGB32);
    img.fill(Qt::red);
    for (int y = 0; y < w; ++y)
        for (int x = w; x < 2 * w; ++x)
            img.setPixel(x, y, qRgba(0, 0, 0, 255));
    QVERIFY(img.save(stem + ".png"));
    writeJson(stem + ".json",
              {{"red", QJsonObject{{"x", 0}, {"y", 0}, {"width", w}, {"height", h}}},
               {"sdf", QJsonObject{{"x", w}, {"y", 0}, {"width", w}, {"height", w}, {"sdf", true}}}});
}
bool isBlank(const QImage& img) {
    if (img.isNull()) return false; // a null image is a load error to QML; the provider gives a blank one
    for (int y = 0; y < img.height(); ++y)
        for (int x = 0; x < img.width(); ++x)
            if (qAlpha(img.pixel(x, y)) != 0) return false;
    return true;
}
}

class TstLegendImages : public QObject {
    Q_OBJECT
private slots:
    void spriteAtLogicalSize() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        writeSheet(base + "@2x", 20, 12);
        LegendImageProvider p([&] { return base; }, [] { return 4.0; });
        QSize size;
        const QImage img = p.requestImage("sprite/red/none", &size, QSize());
        QCOMPARE(img.size(), QSize(10, 6)); // entry px / pixelRatio 2
        QCOMPARE(size, QSize(10, 6));
        QCOMPARE(QColor(img.pixel(5, 3)), QColor(Qt::red));
        // A requested size (QML sourceSize) is honored, drawn from the full-resolution entry.
        QCOMPARE(p.requestImage("sprite/red/none", &size, QSize(20, 12)).size(), QSize(20, 12));
        QCOMPARE(size, QSize(10, 6));
    }
    void oneXSheetUnscaled() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        writeSheet(base, 10, 6);
        LegendImageProvider p([&] { return base; }, [] { return 4.0; });
        QCOMPARE(p.requestImage("sprite/red/none", nullptr, QSize()).size(), QSize(10, 6));
    }
    void sdfTinted() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        writeSheet(base, 8, 8);
        LegendImageProvider p([&] { return base; }, [] { return 4.0; });
        const QImage img = p.requestImage("sprite/sdf/C040C0", nullptr, QSize());
        QCOMPARE(QColor(img.pixel(4, 4)).name(), QStringLiteral("#c040c0"));
        QCOMPARE(QColor(p.requestImage("sprite/sdf/none", nullptr, QSize()).pixel(4, 4)), QColor(Qt::black));
    }
    void unknownOrMissingIsBlank() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        writeSheet(base, 8, 8);
        QString shown = base;
        LegendImageProvider p([&] { return shown; }, [] { return 4.0; });
        QVERIFY(isBlank(p.requestImage("sprite/no-such/none", nullptr, QSize())));
        QVERIFY(isBlank(p.requestImage("sprite/red/zzzzzz", nullptr, QSize()))); // bad tint: still blank, not red
        QVERIFY(isBlank(p.requestImage("nonsense", nullptr, QSize())));
        QVERIFY(isBlank(p.requestImage("overlay/no-such/day", nullptr, QSize())));
        shown = d.filePath("missing"); // a pack whose sprite files are gone
        QVERIFY(isBlank(p.requestImage("sprite/red/none", nullptr, QSize())));
        shown = QString(); // no pack
        QVERIFY(isBlank(p.requestImage("sprite/red/none", nullptr, QSize())));
    }
    void reloadsWhenTheBaseChanges() {
        QTemporaryDir d;
        writeSheet(d.filePath("nav"), 8, 8);
        writeSheet(d.filePath("fish"), 6, 4);
        QString shown = d.filePath("nav");
        LegendImageProvider p([&] { return shown; }, [] { return 4.0; });
        QCOMPARE(p.requestImage("sprite/red/none", nullptr, QSize()).size(), QSize(8, 8));
        shown = d.filePath("fish");
        QCOMPARE(p.requestImage("sprite/red/none", nullptr, QSize()).size(), QSize(6, 4));
    }
    void overlayFromChartIcons() {
        LegendImageProvider p([] { return QString(); }, [] { return 5.0; });
        for (const QString palette : {"day", "night"}) {
            const QImage want = chartIcons(5.0, palette).value("cm-ais-a");
            QVERIFY(!want.isNull());
            QSize size;
            const QImage got = p.requestImage("overlay/cm-ais-a/" + palette, &size, QSize());
            QCOMPARE(got.convertToFormat(QImage::Format_ARGB32), want.convertToFormat(QImage::Format_ARGB32));
            QCOMPARE(size, want.size());
        }
    }
};

QTEST_MAIN(TstLegendImages)
#include "tst_legendimages.moc"
