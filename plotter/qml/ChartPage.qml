import QtQuick
import QtQuick.Controls

// The chart: map, mode toggle, zoom, recenter, "No position" chip and the pack notice.
Item {
    id: page
    required property QtObject chart   // ChartController
    required property Item chartMap    // MapLibreChartMap, created in main.cpp

    // Temporary physical sizing from Screen (px per mm); Task 12 switches to Units.mm and BigButton.
    readonly property real mm: Screen.pixelDensity > 0 ? Screen.pixelDensity : 3.8
    readonly property real buttonSize: Math.max(48, 15 * mm)
    readonly property real margin: 3 * mm

    Item {
        id: mapArea
        anchors.fill: parent
        function zoomBy(factor, point) {
            if (page.chart.follow) page.chart.zoomBy(Math.log2(factor))
            else page.chartMap.scaleBy(factor, point)
        }

        Component.onCompleted: {
            page.chartMap.parent = mapArea
            page.chartMap.anchors.fill = mapArea
        }

        // Gestures are ours, not the map item's. Only a pan stops follow mode; while following, zoom
        // goes through the controller so the boat keeps its place, else it scales about the point.
        DragHandler {
            target: null
            minimumPointCount: 1
            maximumPointCount: 1
            property vector2d last: Qt.vector2d(0, 0)
            onActiveChanged: {
                last = Qt.vector2d(0, 0)
                if (active) page.chartMap.userGesture()
            }
            onActiveTranslationChanged: {
                if (!active) return
                page.chartMap.moveBy(Qt.point(activeTranslation.x - last.x, activeTranslation.y - last.y))
                last = activeTranslation
            }
        }
        PinchHandler {
            target: null
            minimumPointCount: 2
            rotationAxis.enabled: false
            property real last: 1
            onActiveChanged: last = 1
            onActiveScaleChanged: {
                if (!active) return
                mapArea.zoomBy(activeScale / last, centroid.position)
                last = activeScale
            }
        }
        WheelHandler {
            target: null
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: (event) => mapArea.zoomBy(Math.pow(2, event.angleDelta.y / 240), Qt.point(event.x, event.y))
        }
    }

    Button {
        anchors { left: parent.left; top: parent.top; margins: page.margin }
        height: page.buttonSize
        width: Math.max(page.buttonSize * 2.5, implicitWidth)
        font.pixelSize: 4 * page.mm
        enabled: page.chart.fishAvailable
        text: !page.chart.fishAvailable ? "No fishing chart installed"
                                         : (page.chart.mode === "fish" ? "Fishing" : "Navigation")
        onClicked: page.chart.mode = page.chart.mode === "fish" ? "nav" : "fish"
    }

    Column {
        anchors { right: parent.right; verticalCenter: parent.verticalCenter; margins: page.margin }
        spacing: page.margin
        Button {
            width: page.buttonSize; height: page.buttonSize
            font.pixelSize: 8 * page.mm
            text: "+"
            onClicked: page.chart.zoomIn()
        }
        Button {
            width: page.buttonSize; height: page.buttonSize
            font.pixelSize: 8 * page.mm
            text: "−"
            onClicked: page.chart.zoomOut()
        }
    }

    Button {
        anchors { horizontalCenter: parent.horizontalCenter; bottom: noticeBar.top; margins: page.margin }
        visible: !page.chart.follow
        height: page.buttonSize
        width: Math.max(page.buttonSize * 2.5, implicitWidth)
        font.pixelSize: 5 * page.mm
        text: "Recenter"
        onClicked: page.chart.recenter()
    }

    Rectangle {
        anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; margins: page.margin }
        visible: page.chart.noPosition
        radius: height / 2
        color: "#c62828"
        width: chipText.implicitWidth + 6 * page.mm
        height: chipText.implicitHeight + 2 * page.mm
        Label {
            id: chipText
            anchors.centerIn: parent
            text: "No position"
            color: "white"
            font.pixelSize: 5 * page.mm
            font.bold: true
        }
    }

    Rectangle {
        id: noticeBar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: noticeText.implicitHeight + page.mm
        color: "#b0ffffff"
        Label {
            id: noticeText
            anchors.centerIn: parent
            text: page.chart.notice
            color: "black"
            font.pixelSize: Math.max(11, 2.5 * page.mm)
        }
    }
}
