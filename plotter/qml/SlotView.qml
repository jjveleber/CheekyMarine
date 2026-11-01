import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One overlay slot: field label, value at the drawn digit height, unit. Corners stack the label over
// value and unit; Top and Bottom bars run in one line (a position on one line too); Left and Right
// bars stack label, value and unit. It takes taps only in edit mode, so on the chart touches reach
// the map; in edit mode every slot shows, outlined, and an off slot shows its position name, faint.
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
    signal held()

    readonly property bool horizontalBar: slotId === "Top" || slotId === "Bottom"
    readonly property bool verticalBar: slotId === "Left" || slotId === "Right"
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

    objectName: "slot-" + slotId
    enabled: editing
    visible: on || editing
    opacity: on ? 1 : 0.7
    padding: Units.mm(1.5)
    topPadding: Units.mm(1)
    bottomPadding: Units.mm(1.5)

    // Wired by the slot editor (a later task).
    TapHandler {
        longPressThreshold: 0.6
        onLongPressed: slot.held()
    }

    // Centred, so a bar keeps label, value and unit together along its length.
    contentItem: Item {
        implicitWidth: grid.implicitWidth
        implicitHeight: grid.implicitHeight
        GridLayout {
            id: grid
            anchors.centerIn: parent
            rowSpacing: Units.mm(1)
            columnSpacing: Units.mm(1.5)
            // An off slot in edit mode keeps its box (as if on) but shows only its position name.
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
        // The drag handle of the selected slot (the slot editor, a later task).
        Rectangle {
            objectName: "slotHandle"
            visible: slot.selected
            anchors { right: parent.right; bottom: parent.bottom }
            width: Units.mm(4)
            height: width
            color: Theme.editOutline
        }
    }
}
