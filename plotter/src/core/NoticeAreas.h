#pragma once
#include <QByteArray>
#include <QFlags>
#include <QJsonObject>
#include <QList>
#include <QPolygonF>
#include <QString>

// The areas a chart pack's notice applies to (cheekymarine:notice_areas, a GeoJSON FeatureCollection
// whose features carry a `kind`). Only "bc" exists today.
class NoticeAreas {
public:
    enum Kind { None = 0, Bc = 1 };
    Q_DECLARE_FLAGS(Kinds, Kind)

    // Polygons and multipolygons with holes. Invalid or missing JSON gives an empty object; a feature
    // whose kind is not "bc" is skipped.
    static NoticeAreas fromGeoJson(const QByteArray& json);
    void add(const NoticeAreas& other) { m_polygons += other.m_polygons; }
    // The kinds of area the box (degrees) intersects; a box wholly inside a hole does not count.
    Kinds kindsIn(double west, double south, double east, double north) const;
    bool isEmpty() const { return m_polygons.isEmpty(); }
    QByteArray toGeoJson() const;

private:
    struct Polygon {
        Kind kind;
        QPolygonF outer;
        QList<QPolygonF> holes;
    };
    QList<Polygon> m_polygons;
};
Q_DECLARE_OPERATORS_FOR_FLAGS(NoticeAreas::Kinds)

// The notice for the kinds of area on screen: the style's `notices.bc` when Bc is set, else its
// `notice`. `styleMetadata` is the style's metadata.cheekymarine object.
QString pickNotice(const QJsonObject& styleMetadata, NoticeAreas::Kinds kinds);
