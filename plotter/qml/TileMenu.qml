import QtQuick
import QtQuick.Controls.Basic

// The menu a held Home tile opens, over the page (a tap outside it closes it): Edit, Favourite
// on/off, Move left, Move right, Duplicate, Delete, Close. Delete asks first ("Delete <name>?",
// Delete or Keep) and is disabled for the last view. Each action emits its signal; the moves keep
// the menu open, the others close it.
Item {
    id: menu
    property string viewId: ""
    property string name: ""
    property bool favourite: false
    property int index: 0
    property int viewCount: 1
    property real areaWidth: width    // the page left of the tab bar
    property bool confirming: false
    signal editChosen(string id)
    signal favouriteChosen(string id, bool on)
    signal moveChosen(string id, int delta)
    signal duplicateChosen(string id)
    signal deleteChosen(string id)

    objectName: "tileMenu"
    visible: false

    function open(id, name, favourite, index) {
        viewId = id
        menu.name = name
        menu.favourite = favourite
        menu.index = index
        confirming = false
        visible = true
    }
    function close() {
        confirming = false
        visible = false
    }

    MouseArea {
        anchors.fill: parent
        onClicked: menu.close()
    }

    Rectangle {
        id: panel
        x: (menu.areaWidth - width) / 2
        y: (menu.height - height) / 2
        width: content.implicitWidth + 2 * Units.mm(3)
        height: content.implicitHeight + 2 * Units.mm(3)
        radius: Units.mm(1.5)
        color: Theme.background
        border.color: Theme.buttonBorder
        border.width: Math.max(2, Units.mm(0.5))

        MouseArea { anchors.fill: parent } // a tap between the buttons keeps the menu open

        Column {
            id: content
            anchors.centerIn: parent
            spacing: Units.mm(2)

            Label {
                visible: !menu.confirming
                width: grid.width
                text: menu.name
                color: Theme.text
                font.pixelSize: Units.mm(5)
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
            Grid {
                id: grid
                visible: !menu.confirming
                columns: 2
                spacing: Units.mm(1.5)
                readonly property real cell: Units.mm(64)

                BigButton {
                    objectName: "menu-edit"
                    width: grid.cell
                    text: "Edit"
                    onClicked: { menu.close(); menu.editChosen(menu.viewId) }
                }
                BigButton {
                    objectName: "menu-favorite"
                    width: grid.cell
                    text: menu.favourite ? "Favorite off" : "Favorite on"
                    onClicked: { menu.close(); menu.favouriteChosen(menu.viewId, !menu.favourite) }
                }
                BigButton {
                    objectName: "menu-moveLeft"
                    width: grid.cell
                    text: "Move left"
                    enabled: menu.index > 0
                    onClicked: { menu.moveChosen(menu.viewId, -1); menu.index -= 1 }
                }
                BigButton {
                    objectName: "menu-moveRight"
                    width: grid.cell
                    text: "Move right"
                    enabled: menu.index < menu.viewCount - 1
                    onClicked: { menu.moveChosen(menu.viewId, 1); menu.index += 1 }
                }
                BigButton {
                    objectName: "menu-duplicate"
                    width: grid.cell
                    text: "Duplicate"
                    onClicked: { menu.close(); menu.duplicateChosen(menu.viewId) }
                }
                BigButton {
                    objectName: "menu-delete"
                    width: grid.cell
                    enabled: menu.viewCount > 1
                    text: enabled ? "Delete" : "Can't delete the last view"
                    onClicked: menu.confirming = true
                }
                BigButton {
                    objectName: "menu-close"
                    width: grid.cell
                    text: "Close"
                    onClicked: menu.close()
                }
            }

            Label {
                objectName: "menu-deleteQuestion"
                visible: menu.confirming
                width: grid.width
                text: "Delete " + menu.name + "?"
                color: Theme.text
                font.pixelSize: Units.mm(5)
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
            Row {
                visible: menu.confirming
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Units.mm(1.5)
                BigButton {
                    objectName: "menu-deleteYes"
                    width: grid.cell
                    text: "Delete"
                    onClicked: { menu.close(); menu.deleteChosen(menu.viewId) }
                }
                BigButton {
                    objectName: "menu-keep"
                    width: grid.cell
                    text: "Keep"
                    onClicked: menu.confirming = false
                }
            }
        }
    }
}
