#include <QtTest>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>

#include "core/SpriteSheet.h"

namespace {
void writeJson(const QString& path, const QJsonObject& o) {
    QFile f(path);
    QVERIFY(f.open(QIODevice::WriteOnly));
    f.write(QJsonDocument(o).toJson());
}
QJsonObject entry(int x, int y, int w, int h, bool sdf = false) {
    QJsonObject o{{"x", x}, {"y", y}, {"width", w}, {"height", h}, {"pixelRatio", 2}};
    if (sdf)
        o["sdf"] = true;
    return o;
}
}

class TstSpriteSheet : public QObject {
    Q_OBJECT
private slots:
    void loadsTwoXFirst() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        QImage one(8, 8, QImage::Format_ARGB32);
        one.fill(Qt::red);
        QVERIFY(one.save(base + ".png"));
        writeJson(base + ".json", {{"a", entry(0, 0, 4, 4)}});
        QImage two(8, 8, QImage::Format_ARGB32);
        two.fill(Qt::blue);
        QVERIFY(two.save(base + "@2x.png"));
        writeJson(base + "@2x.json", {{"a", entry(0, 0, 8, 8)}});
        auto s = SpriteSheet::load(base);
        QVERIFY(s.has_value());
        QCOMPARE(s->image("a", std::nullopt).size(), QSize(8, 8));
    }
    void fallsBackToOneX() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        QImage one(8, 8, QImage::Format_ARGB32);
        one.fill(Qt::red);
        QVERIFY(one.save(base + ".png"));
        writeJson(base + ".json", {{"a", entry(0, 0, 4, 4)}});
        auto s = SpriteSheet::load(base);
        QVERIFY(s.has_value());
        QCOMPARE(s->image("a", std::nullopt).size(), QSize(4, 4));
    }
    void sdfTinted() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        QImage img(8, 4, QImage::Format_ARGB32);
        img.fill(qRgba(0, 0, 0, 0));
        for (int y = 1; y < 3; ++y)
            for (int x = 1; x < 3; ++x)
                img.setPixel(x, y, qRgba(0, 0, 0, 255));
        for (int y = 0; y < 4; ++y)
            for (int x = 4; x < 8; ++x)
                img.setPixel(x, y, qRgba(0, 0, 0, 191));
        QVERIFY(img.save(base + ".png"));
        writeJson(base + ".json", {{"s", entry(0, 0, 4, 4, true)}, {"e", entry(4, 0, 4, 4, true)}});
        auto s = SpriteSheet::load(base);
        QVERIFY(s.has_value());
        const QImage out = s->image("s", QColor("#ff8000"));
        QCOMPARE(out.size(), QSize(4, 4));
        QCOMPARE(out.pixelColor(1, 1).alpha(), 255);
        QCOMPARE(out.pixelColor(1, 1).red(), 255);
        QCOMPARE(out.pixelColor(1, 1).green(), 128);
        QCOMPARE(out.pixelColor(0, 0).alpha(), 0);
        const QImage edge = s->image("e", QColor("#ff8000"));
        QVERIFY(qAbs(edge.pixelColor(0, 0).alpha() - 128) <= 2);
        QCOMPARE(s->image("s", std::nullopt).pixelColor(1, 1), QColor(0, 0, 0, 255));
    }
    void bakedCroppedAsIs() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        QImage img(6, 6, QImage::Format_ARGB32);
        img.fill(qRgba(1, 2, 3, 4));
        img.setPixel(3, 2, qRgba(10, 20, 30, 200));
        img.setPixel(4, 3, qRgba(50, 60, 70, 255));
        QVERIFY(img.save(base + ".png"));
        writeJson(base + ".json", {{"b", entry(2, 1, 3, 3)}});
        auto s = SpriteSheet::load(base);
        QVERIFY(s.has_value());
        const QImage out = s->image("b", QColor(Qt::green));
        QCOMPARE(out.size(), QSize(3, 3));
        for (int y = 0; y < 3; ++y)
            for (int x = 0; x < 3; ++x)
                QCOMPARE(out.pixel(x, y), img.pixel(x + 2, y + 1));
    }
    void unknownNameIsNull() {
        QTemporaryDir d;
        const QString base = d.filePath("nav");
        QImage img(4, 4, QImage::Format_ARGB32);
        img.fill(Qt::red);
        QVERIFY(img.save(base + ".png"));
        writeJson(base + ".json", {{"a", entry(0, 0, 4, 4)}});
        auto s = SpriteSheet::load(base);
        QVERIFY(s.has_value());
        QVERIFY(s->image("nope", std::nullopt).isNull());
        QVERIFY(!s->contains("nope"));
        QVERIFY(s->contains("a"));
    }
    void missingSheetIsError() {
        QTemporaryDir d;
        const QString base = d.filePath("sprites/nav");
        auto s = SpriteSheet::load(base);
        QVERIFY(!s.has_value());
        QVERIFY(s.error().contains(base));
    }
};

QTEST_GUILESS_MAIN(TstSpriteSheet)
#include "tst_spritesheet.moc"
