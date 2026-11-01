import QtQuick
import QtQuick.Controls.Basic

// Boot splash: the project logo over the whole window, with the app version, the charts and bathy packs
// (version and region) and the nav notice along the bottom, shown for at least `minimumMs`, then it
// hides itself.
Rectangle {
    id: splash
    required property QtObject appInfo // AppInfo
    property int minimumMs: 5000
    // White over the logo by day and dusk; at night the logo is dimmed and the lines take the night red.
    readonly property color infoColor: Theme.palette === "night" ? Theme.text : "#ffffff"

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

    // The project logo fills the splash; the emblem is in the middle of the image, so the crop at
    // the panel's aspect loses none of it.
    Image {
        objectName: "splashLogo"
        anchors.fill: parent
        source: "../assets/CheekyMarine-logo.jpg"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        // The logo's teal would wreck night vision: dim it.
        opacity: Theme.palette === "night" ? 0.3 : 1
    }

    // The info lines along the bottom, over the logo.
    Column {
        anchors { bottom: parent.bottom; bottomMargin: Units.mm(3); horizontalCenter: parent.horizontalCenter }
        width: parent.width - Units.mm(10)
        spacing: Units.mm(1)

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Plotter " + splash.appInfo.appVersion
            color: splash.infoColor
            font.pixelSize: Units.mm(5)
        }
        Label {
            objectName: "splashCharts"
            anchors.horizontalCenter: parent.horizontalCenter
            // No pack in use: either none is installed, or every one was refused (About says why).
            text: splash.packText(splash.appInfo.chartsPack, "Charts",
                                  splash.appInfo.packs.some(p => p.kind === "charts") ? "Charts pack refused: see Settings, About"
                                                                                      : "No charts pack installed")
            color: splash.infoColor
            font.pixelSize: Units.mm(4)
        }
        Label {
            objectName: "splashBathy"
            anchors.horizontalCenter: parent.horizontalCenter
            // A bathy pack can also go unused for another region: only a refused one says so.
            text: splash.packText(splash.appInfo.bathyPack, "Bathy",
                                  splash.appInfo.packs.some(p => p.kind === "bathy" && p.refused !== "") ? "Bathy pack refused: see Settings, About"
                                                                                                         : "No fishing chart installed")
            color: splash.infoColor
            font.pixelSize: Units.mm(4)
        }
        Label {
            objectName: "splashNotice"
            width: parent.width
            visible: text !== ""
            text: splash.appInfo.chartsPack.notice !== undefined ? splash.appInfo.chartsPack.notice : ""
            color: splash.infoColor
            font.pixelSize: Units.mm(3.5)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
        }
    }
}
