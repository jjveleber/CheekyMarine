#include "core/PanPath.h"
#include <QtTest>

class TstPanPath : public QObject {
    Q_OBJECT
private slots:
    void parsesTwoPoints()
    {
        const auto p = parsePanPath("47.9,-122.35,12;48.0,-122.2,14");
        QVERIFY(p.has_value());
        QCOMPARE(p->size(), 2);
        QCOMPARE(p->at(0).lat, 47.9);
        QCOMPARE(p->at(0).lon, -122.35);
        QCOMPARE(p->at(0).zoom, 12.0);
        QCOMPARE(p->at(1).lat, 48.0);
        QCOMPARE(p->at(1).lon, -122.2);
        QCOMPARE(p->at(1).zoom, 14.0);
    }
    void rejectsOnePoint() { QVERIFY(!parsePanPath("47.9,-122.35,12").has_value()); }
    void rejectsBadNumber()
    {
        const auto p = parsePanPath("47.9,x,12;48,-122,13");
        QVERIFY(!p.has_value());
        QVERIFY(p.error().contains("x"));
    }
    void midLegIsLinear()
    {
        const auto path = *parsePanPath("47.9,-122.35,12;48.0,-122.2,14");
        const PanPoint m = panAt(path, 1000, 500);
        QVERIFY(qAbs(m.lat - 47.95) < 1e-9);
        QVERIFY(qAbs(m.lon - -122.275) < 1e-9);
        QVERIFY(qAbs(m.zoom - 13.0) < 1e-9);
    }
    void loopsBackToStart()
    {
        const auto path = *parsePanPath("47.9,-122.35,12;48.0,-122.2,14");
        const PanPoint s = panAt(path, 1000, 2000);
        QCOMPARE(s.lat, 47.9);
        QCOMPARE(s.lon, -122.35);
        QCOMPARE(s.zoom, 12.0);
    }
};

QTEST_MAIN(TstPanPath)
#include "tst_panpath.moc"
