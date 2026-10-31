import QtQuick
import QtQuick.Controls.Basic

// App version, n2kd version (from its hello), the packs in use and the refused packs with reasons.
Item {
    id: page
    required property QtObject appInfo // AppInfo
    signal back()

    objectName: "aboutPage"
    readonly property var refused: appInfo.packs.filter(p => p.refused !== "")

    function packLine(p) {
        return p.kind === undefined ? "" : p.kind + " " + p.region + " " + p.version
    }

    BigButton {
        id: backButton
        objectName: "aboutBack"
        anchors { left: parent.left; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Back"
        onClicked: page.back()
    }

    Flickable {
        anchors { top: backButton.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(3) }
        contentHeight: column.implicitHeight
        clip: true

        Column {
            id: column
            width: parent.width
            spacing: Units.mm(2)

            component Heading: Label {
                color: Theme.text
                font.pixelSize: Units.mm(5)
                font.bold: true
                topPadding: Units.mm(2)
            }
            component Line: Label {
                width: column.width
                color: Theme.text
                font.pixelSize: Units.mm(4)
                wrapMode: Text.Wrap
            }

            Heading { text: "CheekyMarine plotter " + page.appInfo.appVersion }
            Line { text: "n2kd: " + (page.appInfo.daemonVersion !== "" ? page.appInfo.daemonVersion : "not connected") }

            Heading { text: "Packs in use" }
            Line {
                text: page.appInfo.chartsPack.kind !== undefined ? page.packLine(page.appInfo.chartsPack)
                                                                 : "No charts pack installed"
            }
            Line {
                text: page.appInfo.bathyPack.kind !== undefined ? page.packLine(page.appInfo.bathyPack)
                                                                : "No fishing chart installed"
            }

            Heading { text: "Refused packs" }
            Line { visible: page.refused.length === 0; text: "None" }
            Repeater {
                model: page.refused
                Line {
                    required property var modelData
                    text: page.packLine(modelData) + ": " + modelData.refused
                }
            }
        }
    }
}
