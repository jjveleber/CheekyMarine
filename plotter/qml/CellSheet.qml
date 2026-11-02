import QtQuick
import QtQuick.Controls.Basic

// The cell sheet of the view editor: half the page, in the half away from the cell (atTop when the
// cell is in the bottom half). The field grid; a pick emits fieldChosen, Done emits closed.
Rectangle {
    id: sheet
    property string field: "depth"
    property var fieldChoices: []
    property bool atTop: false
    property real rightInset: 0
    signal fieldChosen(string field)
    signal closed()

    objectName: "cellSheet"
    visible: false
    y: atTop ? 0 : parent.height / 2
    width: parent.width - rightInset
    height: parent.height / 2
    color: Theme.background
    border.color: Theme.buttonBorder
    border.width: Math.max(2, Units.mm(0.5))

    // Swallows taps on the sheet, so nothing under it reacts.
    MouseArea { anchors.fill: parent }

    BigButton {
        objectName: "sheetDone"
        anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Done"
        onClicked: sheet.closed()
    }

    Column {
        anchors { top: parent.top; left: parent.left; margins: Units.mm(2) }
        spacing: Units.mm(1.5)
        Label {
            text: "Field"
            color: Theme.text
            font.pixelSize: Units.mm(3.5)
            height: Units.mm(5)
        }
        Grid {
            columns: 3
            spacing: Units.mm(1.5)
            Repeater {
                model: sheet.fieldChoices
                BigButton {
                    required property var modelData
                    objectName: "choice-field-" + modelData.name
                    width: Units.mm(30)
                    text: modelData.label
                    highlighted: sheet.field === modelData.name
                    onClicked: sheet.fieldChosen(modelData.name)
                }
            }
        }
    }
}
