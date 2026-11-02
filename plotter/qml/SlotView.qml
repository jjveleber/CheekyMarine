import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One overlay slot: field label, value at the drawn digit height, unit. Corners stack the label over
// value and unit; Top and Bottom bars run in one line (a position on one line too); Left and Right
// bars stack label, value and unit. It takes taps only in edit mode, so on the chart touches reach
// the map; in edit mode every slot shows, outlined, and an off slot shows its position name, faint.
// The selected slot shows a round 12 mm resize handle centered on its inner corner (a corner slot) or
// the midpoint of its inner edge (a bar), the side towards the page center: half over the slot, half
// over the chart, with a double-headed arrow along the resize axis.
//
// sizeMm is the stored digit height; drawnMm (set by the page from the size clamp) is the one drawn.
// The box is about fixed + per * drawnMm in each axis: the clamp reads fixedWMm, wPerMm, fixedHMm and
// hPerMm, measured from the paddings, label and unit and the field's widest sample, never from
// drawnMm itself.
BigButton {
    id: slot
    property string slotId: "TL"
    property bool on: true
    property string field: "depth"
    property string fieldLabel: "Depth"
    property real sizeMm: 14
    property real drawnMm: sizeMm
    property string formatted: "--"
    property string unit: ""
    property string widestSample: ""
    property bool editing: false
    property bool selected: false
    // The handle dragged: where the clamp's modelled box (below) would put the inner corner, or the
    // inner edge's midpoint, in the parent's (the page's) coordinates.
    signal handleDragged(string slotId, real innerX, real innerY)

    readonly property bool horizontalBar: slotId === "Top" || slotId === "Bottom"
    readonly property bool verticalBar: slotId === "Left" || slotId === "Right"
    // The outer sides, on the page edges: the inner ones face the page centre.
    readonly property bool leftSide: slotId === "TL" || slotId === "BL" || slotId === "Left"
    readonly property bool topSide: slotId === "TL" || slotId === "TR" || slotId === "Top"
    readonly property real outerX: leftSide ? x : x + width
    readonly property real outerY: topSide ? y : y + height
    readonly property string shown: horizontalBar ? formatted.replace("\n", "   ") : formatted

    // The value per mm of digit height: the widest sample's width (one line in a horizontal bar) and
    // its lines at the 1.3 line step.
    readonly property string sampleShown: horizontalBar ? widestSample.replace("\n", "   ") : widestSample
    readonly property int sampleLines: horizontalBar ? 1 : widestSample.split("\n").length
    readonly property real valueWPerMm: Units.textWidthPerDigitMm(sampleShown)
    readonly property real valueHPerMm: 1 + 1.3 * (sampleLines - 1)
    // The parts that do not scale, in mm. The layout rounds each item up to a whole pixel: one pixel
    // more per item keeps the model at or above the drawn box.
    readonly property real px: 1 / Units.pxPerMm
    readonly property real labelWMm: label.implicitWidth / Units.pxPerMm + px
    readonly property real labelHMm: label.implicitHeight / Units.pxPerMm + px
    readonly property bool hasUnit: unit !== ""
    readonly property real unitWMm: hasUnit ? unitLabel.implicitWidth / Units.pxPerMm + px : 0
    readonly property real unitHMm: hasUnit ? unitLabel.implicitHeight / Units.pxPerMm + px : 0
    readonly property real colGapMm: grid.columnSpacing / Units.pxPerMm
    readonly property real rowGapMm: grid.rowSpacing / Units.pxPerMm
    readonly property real padWMm: (leftPadding + rightPadding) / Units.pxPerMm
    readonly property real padHMm: (topPadding + bottomPadding) / Units.pxPerMm
    readonly property real minMm: minimumSize / Units.pxPerMm

    // The box at digit height s, in mm, as the GridLayout below lays it out.
    function widthAtMm(s) {
        // digitPixelSize rounds the font size up by less than a pixel: digitRatio / pxPerMm in mm.
        const v = valueWPerMm * (s + Units.digitRatio * px) + px
        const content = horizontalBar ? labelWMm + colGapMm + v + (hasUnit ? colGapMm + unitWMm : 0)
                      : verticalBar ? Math.max(labelWMm, v, unitWMm)
                      : Math.max(labelWMm, v + (hasUnit ? colGapMm + unitWMm : 0))
        return Math.max(minMm, padWMm + content)
    }
    function heightAtMm(s) {
        const v = valueHPerMm * s + px
        const content = horizontalBar ? Math.max(labelHMm, v, unitHMm)
                      : verticalBar ? labelHMm + rowGapMm + v + (hasUnit ? rowGapMm + unitHMm : 0)
                      : labelHMm + rowGapMm + Math.max(v, unitHMm)
        return Math.max(minMm, padHMm + content)
    }
    // Each axis is convex in s (sums and maxima of lines), so the chord from the 6 mm floor to the
    // stored size lies on or above it over every size the clamp can draw (6 mm to sizeMm).
    readonly property real chordLoMm: 6
    readonly property real chordHiMm: Math.max(sizeMm, chordLoMm + 1)
    readonly property real wPerMm: (widthAtMm(chordHiMm) - widthAtMm(chordLoMm)) / (chordHiMm - chordLoMm)
    readonly property real fixedWMm: widthAtMm(chordLoMm) - wPerMm * chordLoMm
    readonly property real hPerMm: (heightAtMm(chordHiMm) - heightAtMm(chordLoMm)) / (chordHiMm - chordLoMm)
    readonly property real fixedHMm: heightAtMm(chordLoMm) - hPerMm * chordLoMm

    // An off slot in edit mode is a faint outline at the 12 mm control floor with its position name,
    // not a box at its digit height: a 12 mm square for a corner, a 12 mm strip along its edge for a
    // bar (the page sets a bar's length).
    implicitWidth: editing && !on ? minimumSize : Math.max(minimumSize, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: editing && !on ? minimumSize : Math.max(minimumSize, implicitContentHeight + topPadding + bottomPadding)

    objectName: "slot-" + slotId
    enabled: editing
    visible: on || editing
    opacity: on ? 1 : 0.7
    padding: Units.mm(1.5)
    topPadding: Units.mm(1)
    bottomPadding: Units.mm(1.5)

    // The inner corner (a corner slot) or inner edge midpoint (a bar) of the box at the drawn size as
    // the clamp models it, so a drag from it maps back to the drawn size before it moves.
    function modelInner() {
        const w = (fixedWMm + wPerMm * drawnMm) * Units.pxPerMm
        const h = (fixedHMm + hPerMm * drawnMm) * Units.pxPerMm
        return Qt.point(horizontalBar ? x + width / 2 : outerX + (leftSide ? w : -w),
                        verticalBar ? y + height / 2 : outerY + (topSide ? h : -h))
    }

    Item {
        objectName: "handle-" + slot.slotId
        visible: slot.selected
        z: 2
        width: Units.mm(12)
        height: width
        x: slot.horizontalBar ? (slot.width - width) / 2 : slot.leftSide ? slot.width - width / 2 : -width / 2
        y: slot.verticalBar ? (slot.height - height) / 2 : slot.topSide ? slot.height - height / 2 : -height / 2
        // Degrees clockwise from the x axis: the resize axis.
        readonly property real arrowAngle: slot.horizontalBar ? 90 : slot.verticalBar ? 0
                                         : (slot.slotId === "TL" || slot.slotId === "BR") ? 45 : 135
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Theme.editHandleDisc
            opacity: 0.8
        }
        Canvas {
            objectName: "handleArrow-" + slot.slotId
            anchors.fill: parent
            rotation: parent.arrowAngle
            property color stroke: Theme.editHandleArrow
            onStrokeChanged: requestPaint()
            onWidthChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const w = width, cy = height / 2
                const head = 0.14 * w, dy = head * Math.tan(Math.PI / 6)
                ctx.strokeStyle = stroke
                ctx.lineWidth = Math.max(2, Units.mm(0.6))
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(0.22 * w, cy)
                ctx.lineTo(0.78 * w, cy)
                ctx.moveTo(0.22 * w + head, cy - dy)
                ctx.lineTo(0.22 * w, cy)
                ctx.lineTo(0.22 * w + head, cy + dy)
                ctx.moveTo(0.78 * w - head, cy - dy)
                ctx.lineTo(0.78 * w, cy)
                ctx.lineTo(0.78 * w - head, cy + dy)
                ctx.stroke()
            }
        }
        DragHandler {
            target: null
            property point start
            // Once dragging, it keeps the point: the slot under it would take it back on each move.
            grabPermissions: PointerHandler.CanTakeOverFromAnything
            onActiveChanged: if (active) start = slot.modelInner()
            onActiveTranslationChanged: {
                if (active) slot.handleDragged(slot.slotId, start.x + activeTranslation.x, start.y + activeTranslation.y)
            }
        }
    }

    // Centred, so a bar keeps label, value and unit together along its length.
    contentItem: Item {
        // A bar's text is clipped to the bar; the handle, a sibling, is not.
        clip: slot.horizontalBar
        implicitWidth: grid.implicitWidth
        implicitHeight: grid.implicitHeight
        GridLayout {
            id: grid
            anchors.centerIn: parent
            rowSpacing: Units.mm(1)
            columnSpacing: Units.mm(1.5)
            // An off slot in edit mode shows only its position name.
            opacity: slot.on ? 1 : 0

            Label {
                id: label
                Layout.row: 0
                Layout.column: 0
                // Over value and unit in a corner; a span into an empty unit column would add its spacing.
                Layout.columnSpan: slot.horizontalBar || slot.verticalBar || !slot.hasUnit ? 1 : 2
                Layout.alignment: slot.horizontalBar ? Qt.AlignVCenter : (slot.verticalBar ? Qt.AlignHCenter : Qt.AlignLeft)
                text: slot.fieldLabel
                color: Theme.slotLabel
                font.pixelSize: Units.mm(3.5)
            }

            // The value box is exactly the digit height per line; the text is placed by its baseline.
            Item {
                id: valueBox
                Layout.row: slot.verticalBar ? 1 : (slot.horizontalBar ? 0 : 1)
                Layout.column: slot.horizontalBar ? 1 : 0
                Layout.alignment: slot.verticalBar ? Qt.AlignHCenter : Qt.AlignLeft
                readonly property real digit: Units.mm(slot.drawnMm)
                readonly property real lineStep: digit * 1.3
                implicitWidth: value.implicitWidth
                implicitHeight: digit + (value.lineCount - 1) * lineStep
                Label {
                    id: value
                    objectName: "slotValue"
                    y: valueBox.digit - baselineOffset
                    text: slot.shown
                    color: Theme.slotText
                    font.family: Units.fontFamily
                    font.bold: true
                    font.pixelSize: Units.digitPixelSize(slot.drawnMm)
                    lineHeightMode: Text.FixedHeight
                    lineHeight: valueBox.lineStep
                }
            }

            Label {
                id: unitLabel
                Layout.column: slot.verticalBar ? 0 : (slot.horizontalBar ? 2 : 1)
                Layout.alignment: slot.verticalBar ? Qt.AlignHCenter : (Qt.AlignLeft | Qt.AlignBottom)
                Layout.row: slot.verticalBar ? 2 : (slot.horizontalBar ? 0 : 1)
                visible: slot.hasUnit
                text: slot.unit
                color: Theme.slotLabel
                font.pixelSize: Units.mm(4)
            }
        }
        Label {
            objectName: "slotPosition"
            anchors.centerIn: parent
            visible: slot.editing && !slot.on
            opacity: 0.6
            text: slot.slotId
            color: Theme.slotLabel
            font.pixelSize: Units.mm(5)
        }
    }

    background: Rectangle {
        radius: slot.horizontalBar || slot.verticalBar ? 0 : Units.mm(1.5)
        color: Theme.slotBackground
        border.color: Theme.editOutline
        border.width: slot.editing ? Math.max(2, Units.mm(0.6)) : 0
    }
}
