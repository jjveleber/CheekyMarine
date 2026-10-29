// Throwaway spike: QMapLibre::Map rendered in a custom QQuickItem.
#pragma once

#include <QMapLibre/Map>
#include <QMapLibre/Settings>

#include <QQuickItem>
#include <memory>

class MapItem : public QQuickItem {
    Q_OBJECT
public:
    explicit MapItem(QQuickItem* parent = nullptr);
    ~MapItem() override;

    // Created lazily on first use, on the GUI thread.
    QMapLibre::Map* map();
    QMapLibre::Settings settings;

signals:
    void mapChanged(QMapLibre::Map::MapChange change);

protected:
    void geometryChange(const QRectF& newGeometry, const QRectF& oldGeometry) override;
    QSGNode* updatePaintNode(QSGNode* oldNode, UpdatePaintNodeData*) override;

private:
    std::shared_ptr<QMapLibre::Map> m_map;
};
