import QtQuick
import QtQuick.Controls.Basic

// Boot splash: the project logo over the whole window, with the app version, the charts and bathy packs
// (version and region) and the nav notice along the bottom either side of the logo's emblem, shown for
// at least `minimumMs`, then it hides itself.
Rectangle {
    id: splash
    required property QtObject appInfo // AppInfo
    property int minimumMs: 5000
    property bool noticeShown: true // the showChartNotice setting: off leaves the pack's own notice out here (not the pack notices)
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

    // The packs shown of one kind: a single pack reads "Charts: single, region 1.0.0", merged files
    // "Charts: merged, 6 packs, 1.0.0" (the newest version).
    function packText(kind, label, missing) {
        const ps = splash.appInfo.packsInUse.filter(p => p.kind === kind)
        if (ps.length === 0) return missing
        const mode = splash.appInfo.packModes[kind]
        if (mode === undefined || !mode.startsWith("merged")) return label + ": single, " + ps[0].region + " " + ps[0].version
        const newest = ps.map(p => p.version).reduce((a, b) => newer(b, a) ? b : a)
        return label + ": merged, " + ps.length + " packs, " + newest
    }
    function newer(a, b) {
        const x = a.split("."), y = b.split(".")
        for (let i = 0; i < Math.max(x.length, y.length); ++i) {
            const d = (parseInt(x[i]) || 0) - (parseInt(y[i]) || 0)
            if (d !== 0) return d > 0
        }
        return false
    }
    // The first charts pack's notice (when the setting allows; the first on disk that has one, as a gone
    // merged member has none), then the BC line when a data notice applies (also when the setting allows).
    // Then every pack notice line: those are faults to fix, not a disclaimer, so the setting does not hide them.
    readonly property string noticeText: {
        const first = splash.appInfo.packsInUse.find(p => p.kind === "charts" && p.onDisk !== false && p.notice !== "")
        return [first !== undefined && splash.noticeShown ? first.notice : "",
                splash.noticeShown && splash.appInfo.bcInstalled ? "BC: not for navigation. See About for the CHS notice." : ""]
            .concat(splash.appInfo.packNotices)
            .filter(t => t !== "").join("\n")
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
            text: splash.packText("charts", "Charts",
                                  splash.appInfo.packs.some(p => p.kind === "charts") ? "Charts pack refused: see Settings, About"
                                                                                      : "No charts pack installed")
            font.pixelSize: Units.mm(3.5)
        }
        InfoLine {
            objectName: "splashBathy"
            // A bathy pack can also go unused for another region: only a refused one says so.
            text: splash.packText("bathy", "Bathy",
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
        visible: text !== ""
        text: splash.noticeText
        font.pixelSize: Units.mm(3.5)
        horizontalAlignment: Text.AlignRight
    }
}
