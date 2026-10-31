import QtQuick
import QtQuick.Controls.Basic

// Big numbers: 2 to 4 cells splitting the page (2 and 3 side by side, 4 in a 2 x 2 grid). Large
// digits fill each cell; label and unit are small. Tapping a cell picks its field (and the number
// of cells) in the slot editor.
Item {
    id: page
    required property var model // NumbersModel
    readonly property int cellCount: model.count
    readonly property int columns: cellCount === 4 ? 2 : cellCount
    readonly property int rows: cellCount === 4 ? 2 : 1
    readonly property real gap: Units.mm(1)
    property int editIndex: -1

    objectName: "numbersPage"

    // Fewer cells picked while editing one that went away: close the editor, so no field tap can
    // reach a cell that is not there.
    onCellCountChanged: if (editIndex >= cellCount) {
        editIndex = -1
        editor.close()
    }

    Grid {
        id: grid
        anchors { fill: parent; margins: page.gap }
        columns: page.columns
        spacing: page.gap

        Repeater {
            model: page.model
            BigButton {
                id: cell
                required property int index
                required property string field
                required property string fieldLabel
                required property string formatted
                required property string unit

                objectName: "cell-" + index
                width: Math.max(minimumSize, (grid.width - (page.columns - 1) * page.gap) / page.columns)
                height: Math.max(minimumSize, (grid.height - (page.rows - 1) * page.gap) / page.rows)
                padding: Units.mm(2)
                onClicked: {
                    page.editIndex = index
                    editor.title = "Cell " + (index + 1)
                    editor.field = field
                    editor.open()
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
                        font.pixelSize: height
                        minimumPixelSize: Units.mm(4)
                        fontSizeMode: Text.Fit
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                background: Rectangle {
                    radius: Units.mm(1.5)
                    color: cell.down ? Theme.buttonDown : Theme.button
                    border.color: Theme.buttonBorder
                    border.width: 1
                }
            }
        }
    }

    SlotEditor {
        id: editor
        anchors.fill: parent
        showOnOff: false
        showSize: false
        cellCount: page.cellCount
        fieldChoices: page.model.fieldChoices
        onFieldChosen: (f) => page.model.setField(page.editIndex, f)
        onCellCountChosen: (n) => page.model.setCount(n)
    }
}
