import QtQuick
import QtQuick.Controls.Basic

// The right edge: page tabs (Chart, Numbers, Tracks, Settings), then the global controls: touch
// lock, palette cycle (auto, day, dusk, night), and two reserved spaces
// (brightness, MOB).
Rectangle {
    id: bar
    property string current: "chart"
    property string paletteMode: "auto"
    property bool recording: false // track recording on: a dot on the Tracks tab
    signal pageSelected(string page)
    signal paletteCycled()
    signal lockRequested()
    readonly property Item lockButton: lockBtn

    readonly property real tab: Units.mm(15)
    objectName: "tabBar"
    implicitWidth: tab + 2 * Units.mm(1)
    color: Theme.background

    Column {
        id: column
        anchors { fill: parent; margins: Units.mm(1) }
        spacing: Units.mm(1)

        Repeater {
            id: tabs
            model: [{ page: "chart", label: "Chart" }, { page: "numbers", label: "Numbers" },
                    { page: "tracks", label: "Tracks" }, { page: "settings", label: "Settings" }]
            BigButton {
                required property var modelData
                objectName: "tab-" + modelData.page
                width: bar.tab
                height: bar.tab
                leftPadding: Units.mm(0.3)
                rightPadding: Units.mm(0.3)
                font.pixelSize: Units.mm(2.9)
                text: modelData.label
                highlighted: bar.current === modelData.page
                onClicked: bar.pageSelected(modelData.page)
            }
        }

        Item { width: 1; height: Units.mm(2) }

        BigButton {
            id: lockBtn
            objectName: "lockButton"
            width: bar.tab
            font.pixelSize: Units.mm(2.9)
            text: "Lock"
            onClicked: bar.lockRequested()
        }
        BigButton {
            objectName: "paletteButton"
            width: bar.tab
            font.pixelSize: Units.mm(2.9)
            text: bar.paletteMode.charAt(0).toUpperCase() + bar.paletteMode.slice(1)
            onClicked: bar.paletteCycled()
        }
        // Reserved: brightness (plan 5) and MOB (phase 2).
        Item { objectName: "reservedBrightness"; width: bar.tab; height: Units.mm(12) }
        Item { objectName: "reservedMob"; width: bar.tab; height: Units.mm(12) }
    }

    // Over the corner of the Tracks tab, so the column keeps its height.
    Rectangle {
        objectName: "recordIndicator"
        readonly property Item tracksTab: tabs.count > 2 ? tabs.itemAt(2) : null
        visible: bar.recording && tracksTab !== null
        width: Units.mm(2.6)
        height: width
        radius: width / 2
        x: tracksTab ? column.x + tracksTab.x + tracksTab.width - width - Units.mm(1.2) : 0
        y: tracksTab ? column.y + tracksTab.y + Units.mm(1.2) : 0
        color: Theme.alertBackground
        border.color: Theme.buttonText
        border.width: 1
    }
}
