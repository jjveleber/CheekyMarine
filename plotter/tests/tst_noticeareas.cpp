#include "core/NoticeAreas.h"
#include <QtTest>

namespace {
// A 10 x 10 square (0..10) with a 2 x 2 hole (4..6).
const QByteArray kSquare = R"({"type":"FeatureCollection","features":[{"type":"Feature","properties":{"kind":"bc"},
"geometry":{"type":"Polygon","coordinates":[[[0,0],[10,0],[10,10],[0,10],[0,0]],[[4,4],[6,4],[6,6],[4,6],[4,4]]]}}]})";
}

class TstNoticeAreas : public QObject {
    Q_OBJECT
private slots:
    void boxInsidePolygonHits() {
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(1, 1, 2, 2), NoticeAreas::Kinds(NoticeAreas::Bc));
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(8, 8, 12, 12), NoticeAreas::Kinds(NoticeAreas::Bc)); // partial overlap
    }
    void boxOutsideMisses() {
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(11, 11, 12, 12), NoticeAreas::Kinds());
    }
    void boxInsideHoleMisses() {
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(4.5, 4.5, 5.5, 5.5), NoticeAreas::Kinds());
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(3, 3, 5, 5), NoticeAreas::Kinds(NoticeAreas::Bc)); // crosses the hole edge
    }
    void boxTouchingEdgeHits() {
        QCOMPARE(NoticeAreas::fromGeoJson(kSquare).kindsIn(10, 2, 12, 3), NoticeAreas::Kinds(NoticeAreas::Bc));
    }
    void multiPolygonHits() {
        const auto a = NoticeAreas::fromGeoJson(R"({"features":[{"properties":{"kind":"bc"},"geometry":{"type":"MultiPolygon",
"coordinates":[[[[0,0],[1,0],[1,1],[0,1],[0,0]]],[[[5,5],[6,5],[6,6],[5,6],[5,5]]]]}}]})");
        QCOMPARE(a.kindsIn(5.2, 5.2, 5.4, 5.4), NoticeAreas::Kinds(NoticeAreas::Bc));
        QCOMPARE(a.kindsIn(2, 2, 3, 3), NoticeAreas::Kinds());
    }
    void unknownKindIsSkipped() {
        const auto a = NoticeAreas::fromGeoJson(R"({"features":[{"properties":{"kind":"xx"},"geometry":{"type":"Polygon",
"coordinates":[[[0,0],[10,0],[10,10],[0,10],[0,0]]]}}]})");
        QVERIFY(a.isEmpty());
    }
    void invalidJsonIsEmpty() {
        QVERIFY(NoticeAreas::fromGeoJson("not json").isEmpty());
        QVERIFY(NoticeAreas::fromGeoJson("").isEmpty());
        QCOMPARE(NoticeAreas().kindsIn(0, 0, 1, 1), NoticeAreas::Kinds());
    }
    void roundTripKeepsKinds() {
        const auto a = NoticeAreas::fromGeoJson(kSquare);
        const auto b = NoticeAreas::fromGeoJson(a.toGeoJson());
        QVERIFY(!b.isEmpty());
        QCOMPARE(b.kindsIn(1, 1, 2, 2), NoticeAreas::Kinds(NoticeAreas::Bc));
        QCOMPARE(b.kindsIn(4.5, 4.5, 5.5, 5.5), NoticeAreas::Kinds()); // the hole survives
    }
    void addUnions() {
        auto a = NoticeAreas::fromGeoJson(kSquare);
        NoticeAreas e;
        e.add(a);
        QVERIFY(!e.isEmpty());
    }
    void pickNoticeUsesBcOnlyWhenSet() {
        const QJsonObject md{{"notice", "plain"}, {"notices", QJsonObject{{"bc", "bc text"}}}};
        QCOMPARE(pickNotice(md, NoticeAreas::Bc), QString("bc text"));
        QCOMPARE(pickNotice(md, NoticeAreas::None), QString("plain"));
        QCOMPARE(pickNotice(QJsonObject{{"notice", "plain"}}, NoticeAreas::Bc), QString("plain"));
    }
};
QTEST_APPLESS_MAIN(TstNoticeAreas)
#include "tst_noticeareas.moc"
