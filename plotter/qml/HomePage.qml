import QtQuick
import QtQuick.Controls.Basic

// Home: a tile per saved view in order (a tap shows it, a 0.6 s hold opens the tile menu), then
// "+ New view", Tracks, Settings and About. Three columns when each would be at least 40 mm wide,
// else two; the page scrolls when the tiles do not fit.
Item {
    id: page
    required property var views     // ViewsModel
    property real rightInset: 0     // the tab bar strip over the page's right edge
    signal viewSelected(string id)
    signal editView(string id)
    signal newView()
    signal showTracks()
    signal showSettings()
    signal showAbout()

    readonly property real margin: Units.mm(3)
    readonly property real spacing: Units.mm(2)
    readonly property int columns: (width - rightInset - 2 * margin) / 3 >= Units.mm(40) ? 3 : 2
    readonly property real tileW: Math.max(Units.mm(40), (width - rightInset - 2 * margin - (columns - 1) * spacing) / columns)
    readonly property real tileH: Units.mm(36)

    objectName: "homePage"

    component PlainTile: BigButton {
        id: plain
        property string iconName: ""
        width: page.tileW
        height: page.tileH
        font.pixelSize: Units.mm(5)
        font.bold: true
        contentItem: Item {
            Column {
                anchors.centerIn: parent
                width: parent.width
                spacing: Units.mm(1.5)
                Icon {
                    visible: plain.iconName !== ""
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Units.mm(10)
                    height: Units.mm(10)
                    name: plain.iconName
                }
                Label {
                    width: parent.width
                    text: plain.text
                    font: plain.font
                    color: Theme.buttonText
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
            }
        }
    }

    Flickable {
        id: scroller
        anchors { fill: parent; rightMargin: page.rightInset }
        contentWidth: width
        contentHeight: grid.implicitHeight + 2 * page.margin
        clip: true

        Grid {
            id: grid
            x: page.margin
            y: page.margin
            columns: page.columns
            spacing: page.spacing

            Repeater {
                model: page.views
                ViewTile {
                    id: tile
                    required property var model
                    required property int index
                    objectName: "tile-" + model.id
                    width: page.tileW
                    height: page.tileH
                    name: model.name
                    favourite: model.favourite
                    chart: model.chart
                    slots: model.slots
                    layout: model.layout
                    // A property named on... cannot be bound with the plain syntax.
                    Binding { target: tile; property: "onTabBar"; value: tile.model.onTabBar }
                    onTapped: page.viewSelected(model.id)
                    onHeld: menu.open(model.id, model.name, model.favourite, index)
                }
            }
            PlainTile {
                objectName: "tile-new"
                text: "+ New view"
                onClicked: page.newView()
            }
            PlainTile {
                objectName: "tile-tracks"
                iconName: "map"
                text: "Tracks"
                onClicked: page.showTracks()
            }
            PlainTile {
                objectName: "tile-settings"
                iconName: "settings"
                text: "Settings"
                onClicked: page.showSettings()
            }
            PlainTile {
                objectName: "tile-about"
                text: "About"
                onClicked: page.showAbout()
            }
        }
    }

    TileMenu {
        id: menu
        anchors.fill: parent
        areaWidth: page.width - page.rightInset
        viewCount: page.views.count
        onEditChosen: (id) => page.editView(id)
        onFavouriteChosen: (id, on) => page.views.setFavourite(id, on)
        onMoveChosen: (id, delta) => page.views.move(id, delta)
        onDuplicateChosen: (id) => page.views.duplicate(id)
        onDeleteChosen: (id) => page.views.remove(id)
    }
    // Leaving Home closes the menu.
    onVisibleChanged: if (!visible) menu.close()
}
