#include "core/NoticeAreas.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QPainterPath>
#include <QRectF>

namespace {
QPolygonF ring(const QJsonArray& coords) {
    QPolygonF p;
    for (const QJsonValue& c : coords) {
        const QJsonArray xy = c.toArray();
        if (xy.size() >= 2) p << QPointF(xy[0].toDouble(), xy[1].toDouble());
    }
    return p;
}

QJsonArray coords(const QPolygonF& p) {
    QJsonArray out;
    for (const QPointF& pt : p) out.append(QJsonArray{pt.x(), pt.y()});
    return out;
}
} // namespace

NoticeAreas NoticeAreas::fromGeoJson(const QByteArray& json) {
    NoticeAreas out;
    for (const QJsonValue& f : QJsonDocument::fromJson(json).object().value(QStringLiteral("features")).toArray()) {
        const QJsonObject feature = f.toObject();
        if (feature.value(QStringLiteral("properties")).toObject().value(QStringLiteral("kind")).toString()
            != QLatin1String("bc"))
            continue;
        const QJsonObject geom = feature.value(QStringLiteral("geometry")).toObject();
        const QString type = geom.value(QStringLiteral("type")).toString();
        const QJsonArray c = geom.value(QStringLiteral("coordinates")).toArray();
        QJsonArray polygons;
        if (type == QLatin1String("Polygon")) polygons.append(c);
        else if (type == QLatin1String("MultiPolygon")) polygons = c;
        for (const QJsonValue& pv : polygons) {
            const QJsonArray rings = pv.toArray();
            if (rings.isEmpty()) continue;
            Polygon poly{Bc, ring(rings[0].toArray()), {}};
            for (int i = 1; i < rings.size(); ++i) poly.holes << ring(rings[i].toArray());
            out.m_polygons << poly;
        }
    }
    return out;
}

NoticeAreas::Kinds NoticeAreas::kindsIn(double west, double south, double east, double north) const {
    const QRectF box(QPointF(west, south), QPointF(east, north));
    QPolygonF boxPoly(box);
    Kinds kinds;
    for (const Polygon& p : m_polygons) {
        if (kinds.testFlag(p.kind) || !p.outer.intersects(boxPoly)) continue;
        bool inHole = false;
        for (const QPolygonF& h : p.holes) {
            QPainterPath path;
            path.addPolygon(h);
            path.closeSubpath();
            if (path.contains(box)) inHole = true;
        }
        if (!inHole) kinds |= p.kind;
    }
    return kinds;
}

QByteArray NoticeAreas::toGeoJson() const {
    QJsonArray features;
    for (const Polygon& p : m_polygons) {
        QJsonArray rings{coords(p.outer)};
        for (const QPolygonF& h : p.holes) rings.append(coords(h));
        features.append(QJsonObject{{"type", "Feature"},
                                    {"properties", QJsonObject{{"kind", "bc"}}},
                                    {"geometry", QJsonObject{{"type", "Polygon"}, {"coordinates", rings}}}});
    }
    return QJsonDocument(QJsonObject{{"type", "FeatureCollection"}, {"features", features}}).toJson(QJsonDocument::Compact);
}

QString pickNotice(const QJsonObject& styleMetadata, NoticeAreas::Kinds kinds) {
    if (kinds.testFlag(NoticeAreas::Bc)) {
        const QString bc = styleMetadata.value(QStringLiteral("notices")).toObject().value(QStringLiteral("bc")).toString();
        if (!bc.isEmpty()) return bc;
    }
    return styleMetadata.value(QStringLiteral("notice")).toString();
}
