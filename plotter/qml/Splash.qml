import QtQuick
import QtQuick.Controls.Basic

// Boot splash: app version, the charts and bathy packs (version and region) and the nav notice,
// shown for at least `minimumMs`, then it hides itself.
Rectangle {
    id: splash
    required property QtObject appInfo // AppInfo
    property int minimumMs: 2000

    objectName: "splash"
    color: Theme.background

    Timer {
        interval: splash.minimumMs
        running: true
        onTriggered: splash.visible = false
    }
    // Touches during the splash go nowhere.
    MouseArea { anchors.fill: parent }

    function packText(p, kind, missing) {
        return p.version !== undefined ? kind + ": " + p.region + " " + p.version : missing
    }

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - Units.mm(10), Units.mm(170))
        spacing: Units.mm(3)

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "CheekyMarine"
            color: Theme.text
            font.pixelSize: Units.mm(12)
            font.bold: true
        }
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Plotter " + splash.appInfo.appVersion
            color: Theme.text
            font.pixelSize: Units.mm(5)
        }
        Label {
            objectName: "splashCharts"
            anchors.horizontalCenter: parent.horizontalCenter
            // No pack in use: either none is installed, or every one was refused (About says why).
            text: splash.packText(splash.appInfo.chartsPack, "Charts",
                                  splash.appInfo.packs.some(p => p.kind === "charts") ? "Charts pack refused: see Settings, About"
                                                                                      : "No charts pack installed")
            color: Theme.text
            font.pixelSize: Units.mm(4.5)
        }
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: splash.packText(splash.appInfo.bathyPack, "Bathy", "No fishing chart installed")
            color: Theme.text
            font.pixelSize: Units.mm(4.5)
        }
        Label {
            width: parent.width
            visible: text !== ""
            text: splash.appInfo.chartsPack.notice !== undefined ? splash.appInfo.chartsPack.notice : ""
            color: Theme.text
            font.pixelSize: Units.mm(4)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
    }
}
