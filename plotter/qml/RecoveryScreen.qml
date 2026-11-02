import QtQuick
import QtQuick.Controls.Basic

// Shown instead of the app when plotter.db cannot be opened. "Start fresh (keeps a copy)" moves the
// file aside and opens a new one, the only way out without a keyboard; an I/O error also offers
// opening it again. A failure is shown here and nothing else happens.
Rectangle {
    id: screen
    required property QtObject recovery // Recovery

    color: Theme.background

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - Units.mm(10), Units.mm(160))
        spacing: Units.mm(4)

        Label {
            width: parent.width
            text: "The plotter cannot start"
            color: Theme.text
            font.pixelSize: Units.mm(7)
            font.bold: true
            wrapMode: Text.Wrap
        }
        Label {
            width: parent.width
            text: screen.recovery.reason
            color: Theme.text
            font.pixelSize: Units.mm(5)
            wrapMode: Text.Wrap
        }
        Label {
            width: parent.width
            text: "Starting fresh keeps the old file next to the new one and resets settings and tracks."
            color: Theme.text
            font.pixelSize: Units.mm(4)
            wrapMode: Text.Wrap
        }
        Label {
            objectName: "recoveryError"
            width: parent.width
            visible: text !== ""
            text: screen.recovery.error
            color: Theme.alertText
            font.pixelSize: Units.mm(4)
            wrapMode: Text.Wrap
            padding: Units.mm(2)
            background: Rectangle { color: Theme.alertBackground }
        }
        Row {
            spacing: Units.mm(4)
            BigButton {
                objectName: "startFreshButton"
                text: "Start fresh (keeps a copy)"
                onClicked: screen.recovery.startFresh()
            }
            BigButton {
                objectName: "retryButton"
                visible: screen.recovery.canRetry
                text: "Try again"
                onClicked: screen.recovery.retry()
            }
        }
    }
}
