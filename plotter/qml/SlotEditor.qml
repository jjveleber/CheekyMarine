import QtQuick
import QtQuick.Controls.Basic

// Picks a slot's on/off, field and size, or a big numbers cell's field and the number of cells,
// from big lists (no keyboard). Covers its parent while open. Each tap applies at once through the
// signals; Done closes.
Rectangle {
    id: editor
    property string title: ""
    property bool showOnOff: true
    property bool showSize: true
    property int cellCount: 0 // > 0 shows the cells column (big numbers page)
    property var fieldChoices: []
    property bool on: true
    property string field: "depth"
    property string size: "medium"

    signal onChosen(bool on)
    signal fieldChosen(string field)
    signal sizeChosen(string size)
    signal cellCountChosen(int count)

    objectName: "slotEditor"
    visible: false
    color: Theme.background
    function open() { visible = true }
    function close() { visible = false }

    // Swallows touches so nothing underneath reacts while the editor is open.
    MouseArea { anchors.fill: parent }

    Label {
        id: heading
        anchors { left: parent.left; verticalCenter: done.verticalCenter; leftMargin: Units.mm(3) }
        text: editor.title
        color: Theme.text
        font.pixelSize: Units.mm(5)
        font.bold: true
    }
    BigButton {
        id: done
        objectName: "editorDone"
        anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Done"
        onClicked: editor.close()
    }

    Flickable {
        anchors { top: done.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(2) }
        contentWidth: columns.implicitWidth
        contentHeight: columns.implicitHeight
        clip: true

        Row {
            id: columns
            spacing: Units.mm(5)

            component Heading: Label {
                color: Theme.text
                font.pixelSize: Units.mm(3.5)
                height: Units.mm(6)
            }

            Column {
                visible: editor.showOnOff
                spacing: Units.mm(1.5)
                Heading { text: "Show" }
                BigButton {
                    objectName: "choice-on"
                    width: Units.mm(22)
                    text: "On"
                    highlighted: editor.on
                    onClicked: { editor.on = true; editor.onChosen(true) }
                }
                BigButton {
                    objectName: "choice-off"
                    width: Units.mm(22)
                    text: "Off"
                    highlighted: !editor.on
                    onClicked: { editor.on = false; editor.onChosen(false) }
                }
            }

            Column {
                spacing: Units.mm(1.5)
                Heading { text: "Field" }
                Grid {
                    columns: 2
                    spacing: Units.mm(1.5)
                    Repeater {
                        model: editor.fieldChoices
                        BigButton {
                            required property var modelData
                            objectName: "choice-field-" + modelData.name
                            width: Units.mm(32)
                            text: modelData.label
                            highlighted: editor.field === modelData.name
                            onClicked: { editor.field = modelData.name; editor.fieldChosen(modelData.name) }
                        }
                    }
                }
            }

            Column {
                visible: editor.showSize
                spacing: Units.mm(1.5)
                Heading { text: "Size" }
                Repeater {
                    model: [{ name: "small", label: "Small" }, { name: "medium", label: "Medium" }, { name: "large", label: "Large" }]
                    BigButton {
                        required property var modelData
                        objectName: "choice-size-" + modelData.name
                        width: Units.mm(28)
                        text: modelData.label
                        highlighted: editor.size === modelData.name
                        onClicked: { editor.size = modelData.name; editor.sizeChosen(modelData.name) }
                    }
                }
            }

            Column {
                visible: editor.cellCount > 0
                spacing: Units.mm(1.5)
                Heading { text: "Cells" }
                Repeater {
                    model: [2, 3, 4]
                    BigButton {
                        required property int modelData
                        objectName: "choice-cells-" + modelData
                        width: Units.mm(16)
                        text: String(modelData)
                        highlighted: editor.cellCount === modelData
                        onClicked: editor.cellCountChosen(modelData)
                    }
                }
            }
        }
    }
}
