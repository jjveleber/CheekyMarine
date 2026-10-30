import QtQuick
import QtQuick.Controls.Basic

// The right edge: page tabs (Chart, Numbers, Tracks, Settings), then the global controls: touch
// lock (Task 14 wires it), palette cycle (auto, day, dusk, night), and two reserved spaces
// (brightness, MOB).
Rectangle {
    id: bar
    property string current: "chart"
    property string paletteMode: "auto"
    signal pageSelected(string page)
    signal paletteCycled()
    signal lockRequested()

    readonly property real tab: Units.mm(15)
    objectName: "tabBar"
    implicitWidth: tab + 2 * Units.mm(1)
    color: Theme.background

    Column {
        anchors { fill: parent; margins: Units.mm(1) }
        spacing: Units.mm(1)

        Repeater {
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
}
