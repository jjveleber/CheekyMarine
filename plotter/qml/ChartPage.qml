import QtQuick
import QtQuick.Controls.Basic

// The chart: map, overlay slots, mode toggle, zoom, recenter, "No position" chip and the pack
// notice. Bars that are on (Top, Bottom, Left, Right) shrink the chart viewport; the corners float
// over the chart. The notice is the bottom line, under a bottom bar. In edit mode every slot is
// shown outlined (the bars as if on, so nothing overlaps) and tapping one opens the slot editor.
Item {
    id: page
    required property QtObject chart   // ChartController
    required property Item chartMap    // MapLibreChartMap, created in main.cpp
    required property var slotsModel   // SlotsModel
    property bool editing: false

    // Sizes of the bars that take room from the chart (set by the bar slots themselves).
    property real topInset: 0
    property real bottomInset: 0
    property real leftInset: 0
    property real rightInset: 0
    readonly property real margin: Units.mm(1.5)

    objectName: "chartPage"

    Item {
        id: mapArea
        objectName: "mapArea"
        anchors {
            fill: parent
            topMargin: page.topInset
            bottomMargin: page.bottomInset > 0 ? page.bottomInset + noticeBar.height : 0
            leftMargin: page.leftInset
            rightMargin: page.rightInset
        }
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
        // A tap (not a pan) picks the nearest AIS target within 8 mm; a miss changes nothing.
        TapHandler {
            onTapped: (eventPoint) => page.chart.selectAt(eventPoint.position, Units.mm(8))
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

    // Where corners and chart controls go: the map area, above the notice when no bottom bar is on.
    Item {
        id: cornerArea
        anchors {
            top: mapArea.top
            left: mapArea.left
            right: mapArea.right
            bottom: page.bottomInset > 0 ? mapArea.bottom : noticeBar.top
            margins: page.margin
        }
    }

    Rectangle {
        id: noticeBar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: noticeText.implicitHeight + Units.mm(1)
        color: Theme.noticeBackground
        Label {
            id: noticeText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width)
            elide: Text.ElideRight
            text: page.chart.notice
            color: Theme.noticeText
            font.pixelSize: Units.mm(2.8)
        }
    }

    Repeater {
        model: page.slotsModel
        SlotView {
            id: slotView
            // Model roles (not required properties: SlotView declares these names itself).
            slotId: model.slotId
            on: model.on
            field: model.field
            fieldLabel: model.fieldLabel
            size: model.size
            formatted: model.formatted
            unit: model.unit
            readonly property bool takesRoom: on || page.editing

            editing: page.editing
            onClicked: page.slotEditorFor(slotView)

            // The bars span their edge; Left and Right sit between the Top and Bottom bars.
            width: horizontalBar ? Math.max(implicitWidth, page.width) : implicitWidth
            height: verticalBar ? Math.max(implicitHeight, page.height - page.topInset - page.bottomInset - noticeBar.height)
                                : implicitHeight
            x: slotId === "Left" ? 0
             : slotId === "Right" ? page.width - width
             : slotId === "TL" || slotId === "BL" ? cornerArea.x
             : slotId === "TR" || slotId === "BR" ? cornerArea.x + cornerArea.width - width
             : 0
            y: slotId === "Top" ? 0
             : slotId === "Bottom" ? noticeBar.y - height
             : verticalBar ? page.topInset
             : slotId === "TL" || slotId === "TR" ? cornerArea.y
             : cornerArea.y + cornerArea.height - height

            Binding { when: slotView.slotId === "Top"; target: page; property: "topInset"; value: slotView.takesRoom ? slotView.height : 0 }
            Binding { when: slotView.slotId === "Bottom"; target: page; property: "bottomInset"; value: slotView.takesRoom ? slotView.height : 0 }
            Binding { when: slotView.slotId === "Left"; target: page; property: "leftInset"; value: slotView.takesRoom ? slotView.width : 0 }
            Binding { when: slotView.slotId === "Right"; target: page; property: "rightInset"; value: slotView.takesRoom ? slotView.width : 0 }
        }
    }

    function openLegend() { legendSheet.visible = true }

    function slotEditorFor(s) {
        editor.slotId = s.slotId
        editor.title = "Overlay " + s.slotId
        editor.on = s.on
        editor.field = s.field
        editor.size = s.size
        editor.open()
    }

    BigButton {
        objectName: "modeButton"
        anchors { horizontalCenter: cornerArea.horizontalCenter; bottom: cornerArea.bottom }
        visible: !page.editing
        width: Math.max(implicitWidth, Units.mm(30))
        enabled: page.chart.fishAvailable
        text: !page.chart.fishAvailable ? "No fishing chart installed"
                                         : (page.chart.mode === "fish" ? "Fishing" : "Navigation")
        onClicked: page.chart.mode = page.chart.mode === "fish" ? "nav" : "fish"
    }

    BigButton {
        objectName: "recenterButton"
        anchors { horizontalCenter: cornerArea.horizontalCenter; bottom: cornerArea.bottom; bottomMargin: Units.mm(14) }
        visible: !page.chart.follow && !page.editing
        width: Math.max(implicitWidth, Units.mm(30))
        text: "Recenter"
        onClicked: page.chart.recenter()
    }

    Column {
        anchors { right: cornerArea.right; verticalCenter: cornerArea.verticalCenter }
        visible: !page.editing
        spacing: Units.mm(1.5)
        BigButton {
            objectName: "zoomInButton"
            font.pixelSize: Units.mm(8)
            text: "+"
            onClicked: page.chart.zoomIn()
        }
        BigButton {
            objectName: "zoomOutButton"
            font.pixelSize: Units.mm(8)
            text: "−"
            onClicked: page.chart.zoomOut()
        }
    }

    Rectangle {
        anchors { horizontalCenter: cornerArea.horizontalCenter; top: cornerArea.top }
        visible: page.chart.noPosition && !page.editing
        radius: height / 2
        color: Theme.alertBackground
        width: chipText.implicitWidth + Units.mm(6)
        height: chipText.implicitHeight + Units.mm(2)
        Label {
            id: chipText
            anchors.centerIn: parent
            text: "No position"
            color: Theme.alertText
            font.pixelSize: Units.mm(5)
            font.bold: true
        }
    }

    // Left edge, mid-height: clear of the corner slots (top and bottom of the corner area), the
    // zoom column (right) and the centre buttons.
    BigButton {
        objectName: "legendButton"
        anchors { left: cornerArea.left; verticalCenter: cornerArea.verticalCenter }
        visible: !page.editing && page.chart.legend.length > 0 // an empty legend would open a blank sheet
        text: "Legend"
        onClicked: legendSheet.visible = true
    }

    BigButton {
        objectName: "editDoneButton"
        anchors { horizontalCenter: cornerArea.horizontalCenter; verticalCenter: cornerArea.verticalCenter }
        visible: page.editing
        width: Math.max(implicitWidth, Units.mm(40))
        text: "Done editing"
        onClicked: page.editing = false
    }

    AisSheet {
        id: aisSheet
        anchors { horizontalCenter: cornerArea.horizontalCenter; top: cornerArea.top; topMargin: Units.mm(14) }
        info: page.chart.aisSelection
        onClosed: page.chart.clearTarget()
    }

    LegendSheet {
        id: legendSheet
        anchors.fill: parent
        entries: page.chart.legend
        visible: false
        onClosed: visible = false
    }

    SlotEditor {
        id: editor
        property string slotId: ""
        anchors.fill: parent
        fieldChoices: page.slotsModel.fieldChoices
        onOnChosen: (on) => page.slotsModel.setSlot(slotId, on, editor.field, editor.size)
        onFieldChosen: (f) => page.slotsModel.setSlot(slotId, editor.on, f, editor.size)
        onSizeChosen: (s) => page.slotsModel.setSlot(slotId, editor.on, editor.field, s)
    }
}
