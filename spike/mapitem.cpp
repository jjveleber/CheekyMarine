// Throwaway spike: QMapLibre::Map rendered in a custom QQuickItem.
// The render path follows maplibre-native-qt's own TextureNodeOpenGL
// (src/quick/texture_node_opengl.cpp): render into MapLibre's FBO texture on
// the scene graph thread during updatePaintNode, then wrap that GL texture
// in a QSGTexture with no copy.
#include "mapitem.h"

#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QQuickWindow>
#include <QSGSimpleTextureNode>

#include <QElapsedTimer>

std::vector<double> g_renderMs; // map->render() wall time per frame (bench)

namespace {

class MapNode : public QSGSimpleTextureNode {
public:
    explicit MapNode(std::shared_ptr<QMapLibre::Map> map) : m_map(std::move(map)) {}
    ~MapNode() override {
        // Runs on the scene graph thread with the GL context current: the
        // renderer's GL objects must go here, not in ~Map on the GUI thread.
        if (m_rendererCreated) {
            m_map->destroyRenderer();
        }
        if (m_fbo != 0) {
            if (auto* ctx = QOpenGLContext::currentContext()) {
                ctx->functions()->glDeleteFramebuffers(1, &m_fbo);
            }
        }
    }

    void render(QQuickWindow* window, QSize size, qreal dpr) {
        auto* gl = QOpenGLContext::currentContext()->functions();
        if (!m_rendererCreated) {
            m_map->createRenderer(nullptr);
            m_rendererCreated = true;
        }
        if (m_fbo == 0) {
            gl->glGenFramebuffers(1, &m_fbo);
        }
        m_map->resize(size, dpr);
        m_map->updateRenderer(size, dpr, m_fbo);

        GLint prevFbo = 0;
        gl->glGetIntegerv(GL_FRAMEBUFFER_BINDING, &prevFbo);
        window->beginExternalCommands();
        QElapsedTimer t;
        t.start();
        m_map->render();
        gl->glFinish(); // bench only: include GPU time in the measurement
        g_renderMs.push_back(t.nsecsElapsed() / 1e6);
        window->endExternalCommands();
        gl->glBindFramebuffer(GL_FRAMEBUFFER, prevFbo);

        const GLuint tex = m_map->getFramebufferTextureId();
        if (tex > 0 && tex != m_tex) {
            m_tex = tex;
            setTexture(QNativeInterface::QSGOpenGLTexture::fromNative(
                tex, window, size * dpr, QQuickWindow::TextureHasAlphaChannel));
            setOwnsTexture(true); // the QSGTexture wrapper, not the GL texture
            setFiltering(QSGTexture::Linear);
            // GL framebuffer textures are bottom-up.
            setTextureCoordinatesTransform(QSGSimpleTextureNode::MirrorVertically);
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

MapItem::MapItem(QQuickItem* parent) : QQuickItem(parent) {
    setFlag(ItemHasContents, true);
    settings.setCacheDatabasePath(QStringLiteral(":memory:"));
}

MapItem::~MapItem() = default;

QMapLibre::Map* MapItem::map() {
    if (!m_map) {
        const QSize size(qMax(64, int(width())), qMax(64, int(height())));
        m_map = std::make_shared<QMapLibre::Map>(nullptr, settings, size,
                                                 window() ? window()->devicePixelRatio() : 1.0);
        m_map->setConnectionEstablished();
        connect(m_map.get(), &QMapLibre::Map::needsRendering, this, &QQuickItem::update);
        connect(m_map.get(), &QMapLibre::Map::mapChanged, this, &MapItem::mapChanged);
        connect(m_map.get(), &QMapLibre::Map::mapLoadingFailed, this,
                [](QMapLibre::Map::MapLoadingFailure f, const QString& reason) {
                    qWarning() << "mapLoadingFailed" << f << reason;
                });
    }
    return m_map.get();
}

void MapItem::geometryChange(const QRectF& n, const QRectF& o) {
    QQuickItem::geometryChange(n, o);
    update();
}

QSGNode* MapItem::updatePaintNode(QSGNode* oldNode, UpdatePaintNodeData*) {
    if (!m_map || width() < 1 || height() < 1) {
        delete oldNode;
        return nullptr;
    }
    auto* node = static_cast<MapNode*>(oldNode);
    if (!node) {
        node = new MapNode(m_map);
    }
    node->render(window(), QSize(int(width()), int(height())), window()->devicePixelRatio());
    return node;
}
