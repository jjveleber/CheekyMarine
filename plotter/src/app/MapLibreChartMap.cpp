#include "app/MapLibreChartMap.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QQuickWindow>
#include <QSGSimpleTextureNode>
#include <algorithm>
#include <cmath>

namespace {

// Follows maplibre-native-qt's TextureNodeOpenGL: render into MapLibre's FBO on the scene graph
// thread in updatePaintNode, then wrap its GL texture in a QSGTexture.
class MapNode : public QSGSimpleTextureNode {
public:
    explicit MapNode(std::shared_ptr<QMapLibre::Map> map) : m_map(std::move(map)) {}
    ~MapNode() override {
        // Scene graph thread, GL context current: the renderer's GL objects must go here, not in
        // ~Map on the GUI thread (that segfaults on exit).
        if (m_rendererCreated) m_map->destroyRenderer();
        if (m_fbo != 0)
            if (auto* ctx = QOpenGLContext::currentContext()) ctx->functions()->glDeleteFramebuffers(1, &m_fbo);
    }

    void render(QQuickWindow* window, QSize size, qreal dpr) {
        auto* gl = QOpenGLContext::currentContext()->functions();
        if (!m_rendererCreated) {
            m_map->createRenderer(nullptr);
            m_rendererCreated = true;
        }
        if (m_fbo == 0) gl->glGenFramebuffers(1, &m_fbo);
        m_map->resize(size, dpr);
        m_map->updateRenderer(size, dpr, m_fbo);

        GLint prevFbo = 0;
        gl->glGetIntegerv(GL_FRAMEBUFFER_BINDING, &prevFbo);
        window->beginExternalCommands();
        m_map->render();
        window->endExternalCommands();
        gl->glBindFramebuffer(GL_FRAMEBUFFER, prevFbo);

        const GLuint tex = m_map->getFramebufferTextureId();
        if (tex > 0 && tex != m_tex) {
            m_tex = tex;
            setTexture(QNativeInterface::QSGOpenGLTexture::fromNative(tex, window, size * dpr,
                                                                      QQuickWindow::TextureHasAlphaChannel));
            setOwnsTexture(true); // the QSGTexture wrapper, not the GL texture
            setFiltering(QSGTexture::Linear);
            setTextureCoordinatesTransform(QSGSimpleTextureNode::MirrorVertically); // FBO is bottom-up
        }
        setRect(QRectF(QPointF(), size));
        markDirty(QSGNode::DirtyMaterial);
    }

private:
    std::shared_ptr<QMapLibre::Map> m_map;
    GLuint m_fbo = 0;
    GLuint m_tex = 0;
    bool m_rendererCreated = false;
};

} // namespace

MapLibreChartPort::MapLibreChartPort(MapLibreChartMap& item) : m_item(item) {}

void MapLibreChartPort::setStyleJson(const QByteArray& style) {
    // Emits MapChangeDidFinishLoadingStyle (so styleLoaded) synchronously, inside the call.
    m_item.map().setStyleJson(QString::fromUtf8(style));
}

void MapLibreChartPort::setLayerFilter(const QString& layer, const QJsonValue& filter) {
    m_item.map().setFilter(layer, filter.toArray().toVariantList());
}

void MapLibreChartPort::setGeoJson(const QString& source, const QJsonObject& featureCollection) {
    // `data` must be GeoJSON text as a QByteArray; a QVariantMap is not accepted.
    const QByteArray bytes = QJsonDocument(featureCollection).toJson(QJsonDocument::Compact);
    auto& map = m_item.map();
    if (map.sourceExists(source)) map.updateSource(source, QVariantMap{{QStringLiteral("data"), bytes}});
    else map.addSource(source, QVariantMap{{QStringLiteral("type"), QStringLiteral("geojson")},
                                           {QStringLiteral("data"), bytes}});
}

void MapLibreChartPort::addImage(const QString& id, const QImage& image) { m_item.map().addImage(id, image); }

void MapLibreChartPort::addLayer(const QJsonObject& layer) {
    QJsonObject params = layer;
    params.remove(QStringLiteral("id"));
    m_item.map().addLayer(layer.value(QStringLiteral("id")).toString(), params.toVariantMap()); // on top
}

void MapLibreChartPort::setCamera(double lat, double lon, double zoom, double bearingDeg) {
    QMapLibre::CameraOptions c;
    c.center = QVariant::fromValue(QMapLibre::Coordinate(lat, lon));
    c.zoom = zoom;
    c.bearing = bearingDeg;
    m_item.map().jumpTo(c);
}

void MapLibreChartPort::setZoom(double zoom) { m_item.map().setZoom(zoom); }
double MapLibreChartPort::zoom() const { return m_item.map().zoom(); }
double MapLibreChartPort::viewportHeight() const { return m_item.height(); }

QPointF MapLibreChartPort::toScreen(double lat, double lon) const {
    return m_item.map().pixelForCoordinate(QMapLibre::Coordinate(lat, lon));
}

MapLibreChartMap::MapLibreChartMap(QQuickItem* parent) : QQuickItem(parent), m_port(*this) {
    setFlag(ItemHasContents, true);
    m_settings.setCacheDatabasePath(QStringLiteral(":memory:")); // packs are local; no tile cache
    m_map = std::make_shared<QMapLibre::Map>(nullptr, m_settings, QSize(64, 64), 1.0);
    m_map->setConnectionEstablished();
    connect(m_map.get(), &QMapLibre::Map::needsRendering, this, &QQuickItem::update);
    // Connected before the first load: the style-loaded change arrives inside setStyleJson.
    connect(m_map.get(), &QMapLibre::Map::mapChanged, this, [this](QMapLibre::Map::MapChange change) {
        if (change == QMapLibre::Map::MapChangeDidFinishLoadingStyle) emit m_port.styleLoaded();
    });
    connect(m_map.get(), &QMapLibre::Map::mapLoadingFailed, this,
            [](QMapLibre::Map::MapLoadingFailure f, const QString& reason) {
                qWarning() << "MapLibre loading failed" << f << reason;
            });
    connect(this, &MapLibreChartMap::userGesture, &m_port, &ChartMap::userGesture);
}

MapLibreChartMap::~MapLibreChartMap() {
    // A paint node may still hold the Map; nothing it emits may reach this item any more.
    m_map->disconnect(this);
}

void MapLibreChartMap::setZoomRange(double minZoom, double maxZoom) {
    m_minZoom = minZoom;
    m_maxZoom = maxZoom;
}

void MapLibreChartMap::moveBy(QPointF offset) {
    m_map->moveBy(offset);
    update();
}

void MapLibreChartMap::scaleBy(double factor, QPointF centre) {
    if (factor <= 0) return;
    const double z = m_map->zoom();
    const double target = std::clamp(z + std::log2(factor), m_minZoom, m_maxZoom);
    m_map->scaleBy(std::exp2(target - z), centre);
    update();
}

void MapLibreChartMap::geometryChange(const QRectF& newGeometry, const QRectF& oldGeometry) {
    QQuickItem::geometryChange(newGeometry, oldGeometry);
    if (newGeometry.size() != oldGeometry.size() && newGeometry.width() >= 1 && newGeometry.height() >= 1) {
        m_map->resize(newGeometry.size().toSize()); // so camera maths sees the real viewport at once
        emit m_port.viewportChanged();               // the follow camera's lower-third offset depends on it
    }
    update();
}

QSGNode* MapLibreChartMap::updatePaintNode(QSGNode* oldNode, UpdatePaintNodeData*) {
    if (width() < 1 || height() < 1) {
        delete oldNode;
        return nullptr;
    }
    auto* node = static_cast<MapNode*>(oldNode);
    if (!node) node = new MapNode(m_map);
    node->render(window(), QSize(int(width()), int(height())), window()->devicePixelRatio());
    return node;
}
