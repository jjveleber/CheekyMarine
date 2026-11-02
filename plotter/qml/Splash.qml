import QtQuick
import QtQuick.Controls.Basic

// Boot splash: the project logo over the whole window, with the app version, the charts and bathy packs
// (version and region) and the nav notice along the bottom either side of the logo's emblem, shown for
// at least `minimumMs`, then it hides itself.
Rectangle {
    id: splash
    required property QtObject appInfo // AppInfo
    property int minimumMs: 5000
    property bool noticeShown: true // the showChartNotice setting: off leaves the notice line out here too
    // White over the logo by day and dusk; at night the logo is dimmed and the lines take the night red.
    readonly property color infoColor: Theme.palette === "night" ? Theme.text : "#ffffff"
    // The emblem (the round badge) spans the middle half of the 1408 px wide image and almost its full
    // height. The image is drawn at drawnW wide and cropped equally on both sides; the info lines go in
    // the bands left of emblemLeft and right of emblemRight, so they never cover the badge.
    readonly property real drawnW: 1408 * Math.max(width / 1408, height / 768)
    readonly property real emblemLeft: 0.25 * drawnW - (drawnW - width) / 2
    readonly property real emblemRight: width - emblemLeft

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

    // The info lines are outlined in black so they read over the logo's texture.
    component InfoLine: Label {
        width: parent.width
        color: splash.infoColor
        style: Text.Outline
        styleColor: "#000000"
        wrapMode: Text.Wrap
    }

    // Left of the emblem, along the bottom: the version and the packs.
    Column {
        x: Units.mm(3)
        width: splash.emblemLeft - Units.mm(6)
        anchors { bottom: parent.bottom; bottomMargin: Units.mm(3) }
        spacing: Units.mm(1)

        InfoLine {
            text: "Plotter " + splash.appInfo.appVersion
            font.pixelSize: Units.mm(5)
        }
        InfoLine {
            objectName: "splashCharts"
            // No pack in use: either none is installed, or every one was refused (About says why).
            text: splash.packText(splash.appInfo.chartsPack, "Charts",
                                  splash.appInfo.packs.some(p => p.kind === "charts") ? "Charts pack refused: see Settings, About"
                                                                                      : "No charts pack installed")
            font.pixelSize: Units.mm(3.5)
        }
        InfoLine {
            objectName: "splashBathy"
            // A bathy pack can also go unused for another region: only a refused one says so.
            text: splash.packText(splash.appInfo.bathyPack, "Bathy",
                                  splash.appInfo.packs.some(p => p.kind === "bathy" && p.refused !== "") ? "Bathy pack refused: see Settings, About"
                                                                                                         : "No fishing chart installed")
            font.pixelSize: Units.mm(3.5)
        }
    }

    // Right of the emblem, along the bottom: the notice.
    InfoLine {
        objectName: "splashNotice"
        x: splash.emblemRight + Units.mm(3)
        width: splash.width - splash.emblemRight - Units.mm(6)
        anchors { bottom: parent.bottom; bottomMargin: Units.mm(3) }
        visible: splash.noticeShown && text !== ""
        text: splash.appInfo.chartsPack.notice !== undefined ? splash.appInfo.chartsPack.notice : ""
        font.pixelSize: Units.mm(3.5)
        horizontalAlignment: Text.AlignRight
    }
}
