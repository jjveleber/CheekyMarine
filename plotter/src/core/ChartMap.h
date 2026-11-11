#pragma once
#include <QByteArray>
#include <QImage>
#include <QJsonObject>
#include <QJsonValue>
#include <QObject>
#include <QPointF>
#include <QString>

// The chart controller's view of the map. The app implements it over QMapLibre::Map
// (MapLibreChartMap); tests use a fake. A style load drops every runtime image, source and layer.
class ChartMap : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;

    // May emit styleLoaded() synchronously, inside the call.
    virtual void setStyleJson(const QByteArray& style) = 0;
    virtual void setLayerFilter(const QString& layer, const QJsonValue& filter) = 0;
    // Sets a layer's paint property; a null value resets it to the style default.
    virtual void setPaintProperty(const QString& layer, const QString& property, const QJsonValue& value) = 0;
    // Same for a layout property (line-cap is layout, so a paint call cannot change it).
    virtual void setLayoutProperty(const QString& layer, const QString& property, const QJsonValue& value) = 0;
    // Creates the GeoJSON source on the first call after a style load, then updates its data.
    virtual void setGeoJson(const QString& source, const QJsonObject& featureCollection) = 0;
    virtual void addImage(const QString& id, const QImage& image) = 0;
    // `layer` is a style layer object including "id"; it goes above every existing layer, or right
    // below layer `before` when that is given.
    virtual void addLayer(const QJsonObject& layer, const QString& before = {}) = 0;
    virtual void setCamera(double lat, double lon, double zoom, double bearingDeg) = 0;
    // Changes the zoom only (centre and bearing kept).
    virtual void setZoom(double zoom) = 0;
    // Zoom on MapLibre's 512 px world scale (the scale of metresPerPixel).
    virtual double zoom() const = 0;
    // Height of the map viewport in item pixels.
    virtual double viewportHeight() const = 0;
    // Screen position, in item pixels, of a coordinate.
    virtual QPointF toScreen(double lat, double lon) const = 0;

signals:
    void styleLoaded();
    void userGesture(); // a pan by the user (zoom gestures keep follow mode)
    void viewportChanged(); // the viewport size changed (viewportHeight() is the new one)
};
