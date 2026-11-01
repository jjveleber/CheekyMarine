import QtQuick
import QtQuick.Controls.Basic

// The chart of the shown view: map, the view's overlay slots, zoom, recenter, the "No position" and
// "No fishing chart installed" chips and the pack notice. The map runs under the tab bar strip on
// the right (rightInset); everything else stops at its edge. Bars that are on (Top, Bottom, Left,
// Right) shrink the chart viewport; the corners float over the chart. The notice is the bottom line,
// under a bottom bar. Each slot is drawn at its clamped size (PanelMath.drawnSizesMm), so no slot
// leaves the page or runs into another; the stored sizes are not changed. In edit mode every slot is
// shown outlined (the bars as if on, so nothing overlaps) and a tap on one emits slotTapped.
Item {
    id: page
    required property QtObject chart   // ChartController
    required property Item chartMap    // MapLibreChartMap, created in main.cpp
    required property var draft        // ViewDraft
    property real rightInset: 0        // the tab bar strip over the page's right edge
    property bool editing: false
    signal slotTapped(string slotId)
    signal plainTap()                  // a tap on the chart that is not on an AIS target

    // Sizes of the bars that take room from the chart (set by the bar slots themselves).
    property real topInset: 0
    property real bottomInset: 0
    property real leftInset: 0
    property real rightBarInset: 0
    readonly property real margin: Units.mm(1.5)
    // Inner edges of the right corner slots (the corner area's edge when a slot is off): the zoom
    // column sits centred between them, or left of them when the gap is too small.
    property real trBottom: cornerArea.y
    property real brTop: cornerArea.y + cornerArea.height
    property real trLeft: cornerArea.x + cornerArea.width
    property real brLeft: cornerArea.x + cornerArea.width

    // The drawn digit height of each slot by id, from one clamp over every slot's box. The boxes
    // depend on the slots' text metrics and stored sizes only, never on drawnMm, so this does not
    // loop; it is recomputed when a box, the page size or the inset changes.
    readonly property var drawn: drawnSizes()
    function drawnSizes() {
        const boxes = []
        for (let i = 0; i < slotRepeater.count; ++i) {
            const s = slotRepeater.itemAt(i)
            if (!s) continue
            boxes.push({ id: s.slotId, takesRoom: s.takesRoom, sizeMm: s.sizeMm,
                         fixedWMm: s.fixedWMm, wPerMm: s.wPerMm, fixedHMm: s.fixedHMm, hPerMm: s.hPerMm })
        }
        const sizes = PanelMath.drawnSizesMm(boxes, { pageWMm: (page.width - page.rightInset) / Units.pxPerMm,
                                                      pageHMm: (page.height - noticeBar.height) / Units.pxPerMm })
        const out = {}
        for (let i = 0; i < boxes.length; ++i) out[boxes[i].id] = sizes[i]
        return out
    }

    objectName: "chartPage"

    Item {
        id: mapArea
        objectName: "mapArea"
        // Under the strip too, unless a Right bar stands between.
        anchors {
            fill: parent
            topMargin: page.topInset
            bottomMargin: page.bottomInset > 0 ? page.bottomInset + noticeBar.height : 0
            leftMargin: page.leftInset
            rightMargin: page.rightBarInset > 0 ? page.rightInset + page.rightBarInset : 0
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
        // A tap (not a pan) picks the nearest AIS target within 8 mm; a miss changes nothing and is
        // a plain tap.
        TapHandler {
            onTapped: (eventPoint) => {
                const target = page.chart.targetAt(eventPoint.position, Units.mm(8))
                if (target === undefined || target === null) page.plainTap()
                page.chart.selectAt(eventPoint.position, Units.mm(8))
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

    // Where corners and chart controls go: between the bars, above the notice when no bottom bar is
    // on, left of the strip.
    Item {
        id: cornerArea
        objectName: "cornerArea"
        anchors {
            top: mapArea.top
            left: mapArea.left
            right: parent.right
            bottom: page.bottomInset > 0 ? mapArea.bottom : noticeBar.top
            topMargin: page.margin
            leftMargin: page.margin
            rightMargin: page.rightInset + page.rightBarInset + page.margin
            bottomMargin: page.margin
        }
    }

    Rectangle {
        id: noticeBar
        objectName: "noticeBar"
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; rightMargin: page.rightInset }
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
        id: slotRepeater
        model: page.draft.slots
        SlotView {
            id: slotView
            // Model roles (not required properties: SlotView declares these names itself).
            slotId: model.slotId
            on: model.on
            field: model.field
            fieldLabel: model.fieldLabel
            sizeMm: model.sizeMm
            formatted: model.formatted
            unit: model.unit
            widestSample: model.widestSample
            drawnMm: page.drawn[slotId] !== undefined ? page.drawn[slotId] : sizeMm
            readonly property bool takesRoom: on || page.editing

            editing: page.editing
            onClicked: page.slotTapped(slotId)

            // The bars span their edge up to the strip (clipped there); Left and Right sit between
            // the Top and Bottom bars.
            clip: horizontalBar
            width: horizontalBar ? Math.max(minimumSize, page.width - page.rightInset) : implicitWidth
            height: verticalBar ? Math.max(implicitHeight, page.height - page.topInset - page.bottomInset - noticeBar.height)
                                : implicitHeight
            x: slotId === "Left" ? 0
             : slotId === "Right" ? page.width - page.rightInset - width
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
            Binding { when: slotView.slotId === "Right"; target: page; property: "rightBarInset"; value: slotView.takesRoom ? slotView.width : 0 }
            Binding { when: slotView.slotId === "TR"; target: page; property: "trBottom"; value: slotView.on ? slotView.y + slotView.height : cornerArea.y }
            Binding { when: slotView.slotId === "BR"; target: page; property: "brTop"; value: slotView.on ? slotView.y : cornerArea.y + cornerArea.height }
            Binding { when: slotView.slotId === "TR"; target: page; property: "trLeft"; value: slotView.on ? slotView.x : cornerArea.x + cornerArea.width }
            Binding { when: slotView.slotId === "BR"; target: page; property: "brLeft"; value: slotView.on ? slotView.x : cornerArea.x + cornerArea.width }
        }
    }

    function openLegend() { legendSheet.visible = true }

    BigButton {
        objectName: "recenterButton"
        anchors { horizontalCenter: cornerArea.horizontalCenter; bottom: cornerArea.bottom }
        visible: !page.chart.follow && !page.editing
        width: Math.max(implicitWidth, Units.mm(30))
        text: "Recenter"
        onClicked: page.chart.recenter()
    }

    // In the gap between the TR and BR slots. No vertical padding, so each button is 12 mm tall and
    // the column fits between two large corners at 1024x600. A smaller gap (a tall corner, such as
    // the two-line position) puts it left of both corners, at the gap's height inside the area.
    Column {
        readonly property bool fitsGap: page.brTop - page.trBottom >= height
        x: fitsGap ? cornerArea.x + cornerArea.width - width : Math.min(page.trLeft, page.brLeft) - page.margin - width
        y: Math.max(cornerArea.y, Math.min(cornerArea.y + cornerArea.height - height,
                                           page.trBottom + (page.brTop - page.trBottom - height) / 2))
        visible: !page.editing
        spacing: Units.mm(1.5)
        BigButton {
            objectName: "zoomInButton"
            topPadding: 0
            bottomPadding: 0
            font.pixelSize: Units.mm(8)
            text: "+"
            onClicked: page.chart.zoomIn()
        }
        BigButton {
            objectName: "zoomOutButton"
            topPadding: 0
            bottomPadding: 0
            font.pixelSize: Units.mm(8)
            text: "−"
            onClicked: page.chart.zoomOut()
        }
    }

    // Top centre: a Fishing view without a bathy pack says so, then the position chip.
    Column {
        anchors { horizontalCenter: cornerArea.horizontalCenter; top: cornerArea.top }
        spacing: Units.mm(1)
        Rectangle {
            objectName: "noFishChip"
            readonly property string text: fishText.text
            anchors.horizontalCenter: parent.horizontalCenter
            visible: page.draft.chart === "fish" && !page.chart.fishAvailable
            radius: height / 2
            color: Theme.alertBackground
            width: fishText.implicitWidth + Units.mm(6)
            height: fishText.implicitHeight + Units.mm(2)
            // Takes its own tap, so a tap on it is not a plain tap on the map.
            TapHandler { gesturePolicy: TapHandler.WithinBounds }
            Label {
                id: fishText
                anchors.centerIn: parent
                text: "No fishing chart installed"
                color: Theme.alertText
                font.pixelSize: Units.mm(5)
                font.bold: true
            }
        }
        Rectangle {
            objectName: "noPositionChip"
            anchors.horizontalCenter: parent.horizontalCenter
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

    AisSheet {
        id: aisSheet
        anchors { horizontalCenter: cornerArea.horizontalCenter; top: cornerArea.top; topMargin: Units.mm(14) }
        info: page.chart.aisSelection
        onClosed: page.chart.clearTarget()
    }

    LegendSheet {
        id: legendSheet
        anchors { fill: parent; rightMargin: page.rightInset }
        entries: page.chart.legend
        visible: false
        onClosed: visible = false
    }
}
