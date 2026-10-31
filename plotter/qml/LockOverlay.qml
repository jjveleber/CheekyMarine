import QtQuick

// Covers the window while the touch lock is on: every touch, mouse press and wheel turn stops here.
// The one exception is the lock icon, drawn over `anchorItem` (the tab bar's Lock button): holding it
// for 1.5 s unlocks, and a ring shows the progress.
Item {
    id: overlay
    required property QtObject lock // TouchLock
    required property Item anchorItem
    objectName: "lockOverlay"
    visible: lock.locked
    z: 1000

    // The tab bar lays out around us and nothing signals when its Lock button moves on screen, so the
    // icon is placed when shown and then every 100 ms while locked.
    function place() {
        if (!anchorItem) return
        const p = anchorItem.mapToItem(overlay, 0, 0)
        holdTarget.x = p.x
        holdTarget.y = p.y
        holdTarget.width = anchorItem.width
        holdTarget.height = anchorItem.height
    }
    onVisibleChanged: if (visible) place()
    Component.onCompleted: place()
    Timer {
        interval: 100
        repeat: true
        running: overlay.visible
        onTriggered: overlay.place()
    }

    MultiPointTouchArea {
        anchors.fill: parent
        mouseEnabled: true
        minimumTouchPoints: 1
        maximumTouchPoints: 10
        // Past the drag threshold the touch points would be free for the chart's pan and pinch to take.
        onGestureStarted: (gesture) => gesture.grab()
    }
    WheelHandler { }

    Item {
        id: holdTarget
        objectName: "lockHold"

        Rectangle {
            anchors.fill: parent
            radius: Units.mm(1.5)
            color: Theme.button
            border.color: Theme.buttonBorder
            border.width: 1
        }
        // The padlock: a shackle over a body.
        Rectangle {
            id: shackle
            width: parent.width * 0.32
            height: width * 1.1
            radius: width / 2
            anchors { horizontalCenter: parent.horizontalCenter; bottom: body.top; bottomMargin: -radius }
            color: "transparent"
            border.color: Theme.buttonText
            border.width: Math.max(2, Units.mm(0.7))
        }
        Rectangle {
            id: body
            width: parent.width * 0.5
            height: width * 0.75
            radius: Units.mm(0.6)
            anchors { horizontalCenter: parent.horizontalCenter; verticalCenter: parent.verticalCenter; verticalCenterOffset: parent.height * 0.1 }
            color: Theme.buttonText
        }
        Canvas {
            id: ring
            anchors.fill: parent
            property real progress: overlay.lock.holdProgress
            property color stroke: Theme.buttonText
            onProgressChanged: requestPaint()
            onStrokeChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                if (progress <= 0) return
                const r = Math.min(width, height) / 2 - Units.mm(0.6)
                ctx.strokeStyle = stroke
                ctx.lineWidth = Math.max(3, Units.mm(1.2))
                ctx.beginPath()
                ctx.arc(width / 2, height / 2, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * progress)
                ctx.stroke()
            }
        }
        TapHandler {
            gesturePolicy: TapHandler.WithinBounds // takes the touch at once, so the area below never sees it
            onPressedChanged: pressed ? overlay.lock.holdStart() : overlay.lock.holdEnd()
        }
    }
}
