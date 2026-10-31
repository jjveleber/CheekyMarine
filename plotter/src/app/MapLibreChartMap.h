#pragma once
#include "core/ChartMap.h"

#include <QMapLibre/Map>
#include <QMapLibre/Settings>

#include <QQuickItem>
#include <memory>

class MapLibreChartMap;

// The ChartMap seam over the item's QMapLibre::Map. A separate object because ChartMap and
// QQuickItem are both QObjects.
class MapLibreChartPort : public ChartMap {
    Q_OBJECT
public:
    explicit MapLibreChartPort(MapLibreChartMap& item);

    void setStyleJson(const QByteArray& style) override;
    void setLayerFilter(const QString& layer, const QJsonValue& filter) override;
    void setGeoJson(const QString& source, const QJsonObject& featureCollection) override;
    void addImage(const QString& id, const QImage& image) override;
    void addLayer(const QJsonObject& layer) override;
    void setCamera(double lat, double lon, double zoom, double bearingDeg) override;
    void setZoom(double zoom) override;
    double zoom() const override;
    double viewportHeight() const override;
    QPointF toScreen(double lat, double lon) const override;

private:
    MapLibreChartMap& m_item;
};

// QMapLibre::Map rendered in a QQuickItem (spike answer 5): the map draws into its own FBO on the
// scene graph thread and the texture is shown without a copy. The only code that touches MapLibre.
// Gestures live in ChartPage.qml, which calls moveBy/scaleBy and emits userGesture() on a pan.
class MapLibreChartMap : public QQuickItem {
    Q_OBJECT
public:
    explicit MapLibreChartMap(QQuickItem* parent = nullptr);
    ~MapLibreChartMap() override;

    QMapLibre::Map& map() { return *m_map; }
    ChartMap& port() { return m_port; }
    // Range that gestures are clamped to (the controller's minZoom/maxZoom).
    void setZoomRange(double minZoom, double maxZoom);

    Q_INVOKABLE void moveBy(QPointF offset);
    Q_INVOKABLE void scaleBy(double factor, QPointF centre);

signals:
    void userGesture(); // forwarded to port().userGesture()

protected:
    void geometryChange(const QRectF& newGeometry, const QRectF& oldGeometry) override;
    QSGNode* updatePaintNode(QSGNode* oldNode, UpdatePaintNodeData*) override;

private:
    QMapLibre::Settings m_settings;
    std::shared_ptr<QMapLibre::Map> m_map;
    MapLibreChartPort m_port;
    double m_minZoom = 0, m_maxZoom = 22;
};
