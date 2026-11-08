import QtQuick
import QtQuick.Controls.Basic

// Touch color picker for the track line: a saturation/value square and a hue strip, both dragged
// by finger. The preview follows every move; settings.trackColor (#RRGGBB) is written on release,
// on Default and Done, and every 150 ms of a long drag (each write is a synced DB commit). Covers its parent while visible.
Rectangle {
    id: sheet
    required property QtObject settings // Settings
    property string lineType: "dashed"
    property real hue: 0
    property real sat: 0
    property real val: 0.27
    readonly property color chosen: Qt.hsva(hue, sat, val, 1)
    readonly property real thumb: Units.mm(12)

    objectName: "trackColorSheet"
    color: Theme.background
    visible: false

    // Start from the stored color each time the sheet opens.
    onVisibleChanged: if (visible) {
        const c = Qt.color(settings.trackColor)
        hue = Math.max(0, c.hsvHue) // gray reads -1
        sat = c.hsvSaturation
        val = c.hsvValue
    }
    function write() { settings.trackColor = chosen.toString() }
    // During a drag: write at most once per 150 ms.
    function pickMoved() { if (!flushTimer.running) flushTimer.start() }
    function released() { flushTimer.stop(); write() }
    Timer { id: flushTimer; interval: 150; onTriggered: sheet.write() }
    function setDefault() {
        flushTimer.stop()
        settings.trackColor = "#444444"
        const c = Qt.color("#444444")
        hue = 0; sat = c.hsvSaturation; val = c.hsvValue
    }

    MouseArea { anchors.fill: parent } // swallow touches

    Label {
        anchors { left: parent.left; verticalCenter: doneButton.verticalCenter; leftMargin: Units.mm(3) }
        text: "Track color"
        color: Theme.text
        font.pixelSize: Units.mm(5)
        font.bold: true
    }
    BigButton {
        id: doneButton
        objectName: "trackColorDone"
        anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Done"
        onClicked: { if (flushTimer.running) { flushTimer.stop(); sheet.write() } sheet.visible = false }
    }
    BigButton {
        objectName: "trackColorDefault"
        anchors { right: doneButton.left; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Default"
        onClicked: sheet.setDefault()
    }

    Canvas {
        id: preview
        objectName: "trackColorPreview"
        property color lineColor: sheet.chosen
        property string lineType: sheet.lineType
        anchors { left: parent.left; right: parent.right; top: doneButton.bottom; margins: Units.mm(3) }
        height: Units.mm(8)
        onLineColorChanged: requestPaint()
        onLineTypeChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const w = Units.mm(1.2)
            const patterns = { solid: [], dashed: [4, 2], dotted: [1, 2], dashdot: [4, 2, 1, 2] }
            ctx.strokeStyle = lineColor
            ctx.lineWidth = w
            ctx.lineCap = "butt"
            ctx.setLineDash((patterns[lineType] || []).map(x => x * w))
            ctx.beginPath()
            ctx.moveTo(0, height / 2)
            ctx.lineTo(width, height / 2)
            ctx.stroke()
        }
    }

    Item {
        id: pickers
        anchors { left: parent.left; right: parent.right; top: preview.bottom; bottom: parent.bottom; margins: Units.mm(3) }
        readonly property real stripW: Units.mm(14)
        readonly property real side: Math.max(sheet.thumb * 2, Math.min(width - stripW - Units.mm(6), height))

        // Saturation (left to right) and value (top to bottom) at the current hue.
        Rectangle {
            id: svSquare
            objectName: "trackColorSv"
            width: pickers.side
            height: pickers.side
            color: Qt.hsva(sheet.hue, 1, 1, 1)
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "white" }
                    GradientStop { position: 1; color: "transparent" }
                }
            }
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: "black" }
                }
            }
            Thumb { x: sheet.sat * svSquare.width - width / 2; y: (1 - sheet.val) * svSquare.height - height / 2 }
            MouseArea {
                anchors.fill: parent
                function pick(m) {
                    sheet.sat = Math.max(0, Math.min(1, m.x / width))
                    sheet.val = Math.max(0, Math.min(1, 1 - m.y / height))
                    sheet.pickMoved()
                }
                onPressed: m => pick(m)
                onPositionChanged: m => pick(m)
                onReleased: sheet.released()
            }
        }

        // Hue, top to bottom.
        Rectangle {
            id: hueStrip
            objectName: "trackColorHue"
            x: svSquare.width + Units.mm(6)
            width: pickers.stripW
            height: pickers.side
            gradient: Gradient {
                GradientStop { position: 0 / 6; color: "#FF0000" }
                GradientStop { position: 1 / 6; color: "#FFFF00" }
                GradientStop { position: 2 / 6; color: "#00FF00" }
                GradientStop { position: 3 / 6; color: "#00FFFF" }
                GradientStop { position: 4 / 6; color: "#0000FF" }
                GradientStop { position: 5 / 6; color: "#FF00FF" }
                GradientStop { position: 6 / 6; color: "#FF0000" }
            }
            Thumb { x: (hueStrip.width - width) / 2; y: sheet.hue * hueStrip.height - height / 2 }
            MouseArea {
                anchors.fill: parent
                function pick(m) {
                    sheet.hue = Math.max(0, Math.min(1, m.y / height))
                    sheet.pickMoved()
                }
                onPressed: m => pick(m)
                onPositionChanged: m => pick(m)
                onReleased: sheet.released()
            }
        }
    }

    component Thumb: Rectangle {
        width: sheet.thumb
        height: sheet.thumb
        radius: width / 2
        color: "transparent"
        border.color: "white"
        border.width: Units.mm(1)
        Rectangle { anchors.fill: parent; anchors.margins: -Units.mm(0.5); radius: width / 2; color: "transparent"; border.color: "black"; border.width: 1 }
    }
}
