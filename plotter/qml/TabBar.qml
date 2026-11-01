import QtQuick
import QtQuick.Controls.Basic

// The right edge, top to bottom: one tab per favourite view that fits (tabViews), the house tab
// (Home), a 2 mm gap, then the global controls: touch lock and palette cycle (auto, day, dusk,
// night). Main sizes tabViews to what fits, so the column never scrolls. A tap on a view tab
// selects it, a 0.6 s hold emits viewHeld; every button press emits touched. Main binds x to shown:
// the bar slides in or out in 150 ms, and a press on it during the slide (or between its buttons)
// only emits touched.
Rectangle {
    id: bar
    property var tabViews: []          // [{id, shortName, icon}]
    property string currentId: ""      // the shown view's id: its tab is highlighted
    property bool homeHighlighted: false
    property string paletteMode: "auto"
    property bool recording: false     // track recording on: a dot on the house tab's corner
    property bool shown: true
    signal viewSelected(string id)
    signal viewHeld(string id)
    signal homeSelected()
    signal lockRequested()
    signal paletteCycled()
    signal touched()
    readonly property Item lockButton: lockBtn

    readonly property real tab: Units.mm(15)
    objectName: "tabBar"
    implicitWidth: tab + 2 * Units.mm(1)
    color: Theme.background
    Behavior on x { NumberAnimation { id: slide; duration: 150 } }

    // Under the buttons, it takes the presses between them; over them while the bar slides.
    MouseArea {
        anchors.fill: parent
        z: slide.running ? 1 : -1
        onPressed: bar.touched()
    }

    Column {
        id: column
        anchors {
            fill: parent
            margins: Units.mm(1)
        }
        spacing: Units.mm(1)

        Repeater {
            model: bar.tabViews
            BigButton {
                id: viewTab
                required property var modelData
                property bool wasHeld: false
                objectName: "tab-view-" + modelData.id
                width: bar.tab
                height: bar.tab
                padding: Units.mm(0.3)
                highlighted: modelData.id === bar.currentId
                onPressed: { wasHeld = false; bar.touched() }
                onClicked: if (!wasHeld) bar.viewSelected(modelData.id)
                contentItem: Column {
                    spacing: Units.mm(0.3)
                    topPadding: (viewTab.availableHeight - icon.height - name.implicitHeight - spacing) / 2
                    Icon {
                        id: icon
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Units.mm(6.5)
                        height: Units.mm(6.5)
                        name: viewTab.modelData.icon
                    }
                    Label {
                        id: name
                        width: parent.width
                        text: viewTab.modelData.shortName
                        color: Theme.buttonText
                        font.pixelSize: Units.mm(2.9)
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                }
                TapHandler {
                    longPressThreshold: 0.6
                    onLongPressed: {
                        viewTab.wasHeld = true
                        bar.viewHeld(viewTab.modelData.id)
                    }
                }
            }
        }

        BigButton {
            id: homeTab
            objectName: "tab-home"
            width: bar.tab
            height: bar.tab
            highlighted: bar.homeHighlighted
            onPressed: bar.touched()
            onClicked: bar.homeSelected()
            contentItem: Item {
                Icon {
                    anchors.centerIn: parent
                    width: Units.mm(7.5)
                    height: Units.mm(7.5)
                    name: "home"
                }
            }
        }

        Item { width: 1; height: Units.mm(2) }

        BigButton {
            id: lockBtn
            objectName: "lockButton"
            width: bar.tab
            font.pixelSize: Units.mm(2.9)
            text: "Lock"
            onPressed: bar.touched()
            onClicked: bar.lockRequested()
        }
        BigButton {
            objectName: "paletteButton"
            width: bar.tab
            font.pixelSize: Units.mm(2.9)
            text: bar.paletteMode.charAt(0).toUpperCase() + bar.paletteMode.slice(1)
            onPressed: bar.touched()
            onClicked: bar.paletteCycled()
        }
    }

    // Over the corner of the house tab, so the column keeps its height.
    Rectangle {
        objectName: "recordIndicator"
        visible: bar.recording
        width: Units.mm(2.6)
        height: width
        radius: width / 2
        x: column.x + homeTab.x + homeTab.width - width - Units.mm(1.2)
        y: column.y + homeTab.y + Units.mm(1.2)
        color: Theme.alertBackground
        border.color: Theme.buttonText
        border.width: 1
    }
}
