import QtQuick
import QtQuick.Controls.Basic

// App version, n2kd version (from its hello), the packs in use and the refused packs with reasons.
Item {
    id: page
    required property QtObject appInfo // AppInfo
    property real rightInset: 0        // the tab bar strip over the page's right edge
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
        anchors { top: backButton.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(3); rightMargin: Units.mm(3) + page.rightInset }
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
            Line {
                objectName: "aboutSet"
                text: page.appInfo.setVersion !== "" ? "Set: cheekymarine " + page.appInfo.setVersion
                                                     : "Set: none (not installed from a set)"
            }
            Line { text: "n2kd: " + (page.appInfo.daemonVersion !== "" ? page.appInfo.daemonVersion : "not connected") }

            Heading { text: "Chart packs" }
            Line { visible: page.appInfo.packsInUse.length === 0; text: "No chart packs installed" }
            Repeater {
                model: page.appInfo.packsInUse
                Line {
                    required property var modelData
                    objectName: "aboutPackLine"
                    text: page.packLine(modelData)
                }
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
