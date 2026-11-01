#pragma once
#include "core/Views.h"
#include <QColor>
#include <QDebug>
#include <QFile>
#include <QObject>
#include <QUrl>
#include <QtQml/qqmlregistration.h>

// The bundled Tabler icons (icons/tabler/*.svg) for QML. source() tints an icon by replacing
// currentColor and hands it to Image as a data URL, so Image needs no file access and the colour
// follows the Theme palette (red at night).
class IconsQml : public QObject {
    Q_OBJECT
    QML_NAMED_ELEMENT(Icons)
    QML_SINGLETON

public:
    using QObject::QObject;

    Q_INVOKABLE QStringList names() const { return iconNames(); }

    Q_INVOKABLE QUrl source(const QString& name, const QColor& color) const {
        if (name.isEmpty()) return {};  // an Icon before its name is set
        if (!iconNames().contains(name)) {
            qWarning() << "Icons: unknown icon" << name;
            return {};
        }
        QFile f(QStringLiteral(":/qt/qml/CheekyMarine/icons/tabler/%1.svg").arg(name));
        if (!f.open(QIODevice::ReadOnly)) {
            qWarning() << "Icons: cannot read icon" << name;
            return {};
        }
        const QByteArray svg = f.readAll().replace("currentColor", color.name().toUtf8());
        return QUrl(QStringLiteral("data:image/svg+xml;utf8,") + QString::fromLatin1(QUrl::toPercentEncoding(QString::fromUtf8(svg))),
                    QUrl::StrictMode);
    }
};
