import QtQuick
import QtQuick.Controls.Basic

// A view's Home tile: its thumbnail, the name under it, a star top-right on a favorite, and
// "Not on tab bar (full)" on a favorite the tab bar has no room for. A tap emits tapped, a 0.6 s
// hold emits held (and no tap).
BigButton {
    id: tile
    property string name: ""
    property bool favorite: false
    property bool onTabBar: false
    property string chart: "nav"
    property var slots: []
    property string layout: ""
    property bool wasHeld: false
    signal tapped()
    signal held()

    onPressed: wasHeld = false
    onClicked: if (!wasHeld) tapped()

    TapHandler {
        longPressThreshold: 0.6
        onLongPressed: {
            tile.wasHeld = true
            tile.held()
        }
    }

    contentItem: Item {
        ViewThumb {
            anchors { top: parent.top; horizontalCenter: parent.horizontalCenter }
            height: Math.max(Units.mm(12), parent.height - nameLabel.height - note.height - Units.mm(1))
            // The page's shape, as wide as the tile allows.
            width: Math.min(parent.width, height * Units.windowWidth / Math.max(1, Units.windowHeight))
            chart: tile.chart
            slots: tile.slots
            layout: tile.layout
        }
        Label {
            id: nameLabel
            anchors { left: parent.left; right: parent.right; bottom: note.top }
            text: tile.name
            color: Theme.buttonText
            font.pixelSize: Units.mm(4.5)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        Label {
            id: note
            objectName: "tileNote"
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            // Keeps its line when hidden (anchors still lay it out), so every thumbnail is the same size.
            visible: tile.favorite && !tile.onTabBar
            text: "Not on tab bar (full)"
            color: Theme.buttonText
            font.pixelSize: Units.mm(3.2)
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        Icon {
            objectName: "tileStar"
            anchors { top: parent.top; right: parent.right }
            visible: tile.favorite
            width: Units.mm(6)
            height: Units.mm(6)
            name: "star"
        }
    }
}
