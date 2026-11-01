import QtQuick
import QtQuick.Controls.Basic

// A view with no chart: its cells tile the page (left of the tab bar strip) by the view's layout,
// 1 mm apart. Large digits fill each cell; label and unit are small. In edit mode the cells are
// outlined and a tap on one emits cellTapped; otherwise any tap is a plain tap, and a 0.6 s hold on a
// cell emits cellHeld (and no tap).
Item {
    id: page
    required property var draft     // ViewDraft
    property real rightInset: 0     // the tab bar strip over the page's right edge
    property bool editing: false
    signal cellTapped(int index)
    signal cellHeld(int index)
    signal plainTap()

    readonly property real gap: Units.mm(1)
    readonly property var rects: Layouts.rects(draft.layout)
    readonly property real areaW: width - rightInset

    objectName: "cellPage"

    MouseArea {
        anchors.fill: parent
        onClicked: page.plainTap()
    }

    function cellItem(index) { return cellRepeater.itemAt(index) }

    Repeater {
        id: cellRepeater
        model: page.draft.cells
        BigButton {
            id: cell
            required property int index
            required property string field
            required property string fieldLabel
            required property string formatted
            required property string unit
            // Fractions of the page; a gap at every edge and between neighbours.
            readonly property var rect: index < page.rects.length ? page.rects[index] : null

            objectName: "cell-" + index
            visible: rect !== null
            x: rect ? page.gap + rect.x * (page.areaW - page.gap) : 0
            y: rect ? page.gap + rect.y * (page.height - page.gap) : 0
            // Never under the 12 mm minimum, as before the page is first laid out.
            width: Math.max(minimumSize, rect ? rect.w * (page.areaW - page.gap) - page.gap : 0)
            height: Math.max(minimumSize, rect ? rect.h * (page.height - page.gap) - page.gap : 0)
            padding: Units.mm(2)
            property bool wasHeld: false
            onPressed: wasHeld = false
            onClicked: {
                if (page.editing) page.cellTapped(index)
                else if (!wasHeld) page.plainTap()
            }
            TapHandler {
                enabled: !page.editing
                longPressThreshold: 0.6
                gesturePolicy: TapHandler.DragThreshold
                onLongPressed: {
                    cell.wasHeld = true
                    page.cellHeld(cell.index)
                }
            }

            contentItem: Item {
                Label {
                    id: label
                    anchors { left: parent.left; top: parent.top }
                    text: cell.fieldLabel
                    color: Theme.slotLabel
                    font.pixelSize: Units.mm(5)
                }
                Label {
                    id: unitLabel
                    anchors { right: parent.right; bottom: parent.bottom }
                    text: cell.unit
                    color: Theme.slotLabel
                    font.pixelSize: Units.mm(5)
                }
                Label {
                    // Side margins keep neighbouring cells' digits from reading as one number.
                    anchors {
                        left: parent.left; right: parent.right; top: label.bottom; bottom: unitLabel.top
                        leftMargin: Units.mm(4); rightMargin: Units.mm(4)
                    }
                    text: cell.formatted
                    color: Theme.slotText
                    font.family: Units.fontFamily
                    font.bold: true
                    font.pixelSize: Math.max(Units.mm(4), height)
                    minimumPixelSize: Units.mm(4)
                    fontSizeMode: Text.Fit
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
            background: Rectangle {
                radius: Units.mm(1.5)
                color: cell.down ? Theme.buttonDown : Theme.button
                border.color: page.editing ? Theme.editOutline : Theme.buttonBorder
                border.width: page.editing ? Math.max(2, Units.mm(0.6)) : 1
            }
        }
    }
}
