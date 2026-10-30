import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One overlay slot: field label, value at the slot size's digit height, unit. Corners stack the
// label over value and unit; Top and Bottom bars run in one line (a position on one line too);
// Left and Right bars stack label, value and unit. It takes taps only in edit mode, so on the chart
// touches reach the map; in edit mode every slot shows, outlined, and an off slot is dimmed.
BigButton {
    id: slot
    property string slotId: "TL"
    property bool on: true
    property string field: "depth"
    property string fieldLabel: "Depth"
    property string size: "medium"
    property string formatted: "--"
    property string unit: ""
    property bool editing: false

    readonly property bool horizontalBar: slotId === "Top" || slotId === "Bottom"
    readonly property bool verticalBar: slotId === "Left" || slotId === "Right"
    readonly property real digitMm: Units.slotDigitMm(size)
    readonly property string shown: horizontalBar ? formatted.replace("\n", "   ") : formatted

    objectName: "slot-" + slotId
    enabled: editing
    visible: on || editing
    opacity: on ? 1 : 0.7
    padding: Units.mm(1.5)
    topPadding: Units.mm(1)
    bottomPadding: Units.mm(1.5)

    // Centred, so a bar keeps label, value and unit together along its length.
    contentItem: Item {
        implicitWidth: grid.implicitWidth
        implicitHeight: grid.implicitHeight
        GridLayout {
            id: grid
            anchors.centerIn: parent
            rowSpacing: Units.mm(1)
            columnSpacing: Units.mm(1.5)

            Label {
                Layout.row: 0
                Layout.column: 0
                Layout.columnSpan: slot.horizontalBar || slot.verticalBar ? 1 : 2
                Layout.alignment: slot.horizontalBar ? Qt.AlignVCenter : (slot.verticalBar ? Qt.AlignHCenter : Qt.AlignLeft)
                text: slot.on ? slot.fieldLabel : slot.fieldLabel + " (off)"
                color: Theme.slotLabel
                font.pixelSize: Units.mm(3.5)
            }

            // The value box is exactly the digit height per line; the text is placed by its baseline.
            Item {
                id: valueBox
                Layout.row: slot.verticalBar ? 1 : (slot.horizontalBar ? 0 : 1)
                Layout.column: slot.horizontalBar ? 1 : 0
                Layout.alignment: slot.verticalBar ? Qt.AlignHCenter : Qt.AlignLeft
                readonly property real digit: Units.mm(slot.digitMm)
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
                    font.pixelSize: Units.digitPixelSize(slot.digitMm)
                    lineHeightMode: Text.FixedHeight
                    lineHeight: valueBox.lineStep
                }
            }

            Label {
                Layout.column: slot.verticalBar ? 0 : (slot.horizontalBar ? 2 : 1)
                Layout.alignment: slot.verticalBar ? Qt.AlignHCenter : (Qt.AlignLeft | Qt.AlignBottom)
                Layout.row: slot.verticalBar ? 2 : (slot.horizontalBar ? 0 : 1)
                visible: slot.unit !== ""
                text: slot.unit
                color: Theme.slotLabel
                font.pixelSize: Units.mm(4)
            }
        }
    }

    background: Rectangle {
        radius: slot.horizontalBar || slot.verticalBar ? 0 : Units.mm(1.5)
        color: Theme.slotBackground
        border.color: Theme.editOutline
        border.width: slot.editing ? Math.max(2, Units.mm(0.6)) : 0
    }
}
