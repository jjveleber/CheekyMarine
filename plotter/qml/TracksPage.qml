import QtQuick
import QtQuick.Controls.Basic

// Track recording on and off, and the recorded tracks: show or hide each on the chart, delete with
// a confirm (an item in this page, not a dialog: the touch lock overlay must stay on top of everything).
Item {
    id: page
    required property QtObject tracks   // TracksController
    required property QtObject settings // Settings

    objectName: "tracksPage"

    property var pendingId: 0
    property string pendingName: ""

    function durationText(s) {
        const min = Math.round(s / 60)
        if (s < 60) return Math.round(s) + " s"
        if (min < 60) return min + " min"
        return Math.floor(min / 60) + " h " + (min % 60) + " min"
    }
    function nmText(m) { return (m / 1852).toFixed(1) + " nm" }

    Component.onCompleted: tracks.refresh()
    onVisibleChanged: if (visible) tracks.refresh()
    // The recording track grows while the page is open.
    Timer {
        interval: 5000
        repeat: true
        running: page.visible
        onTriggered: page.tracks.refresh()
    }

    BigButton {
        id: recordButton
        objectName: "recordButton"
        anchors { left: parent.left; top: parent.top; margins: Units.mm(3) }
        width: Math.max(implicitWidth, Units.mm(50))
        text: page.settings.trackRecording ? "Stop recording" : "Start recording"
        highlighted: page.settings.trackRecording
        onClicked: page.settings.trackRecording = !page.settings.trackRecording
    }

    Label {
        objectName: "noTracks"
        anchors { top: recordButton.bottom; left: parent.left; margins: Units.mm(3) }
        visible: page.tracks.tracks.length === 0
        text: "No tracks yet"
        color: Theme.text
        font.pixelSize: Units.mm(4.5)
    }

    Flickable {
        anchors { top: recordButton.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(3) }
        contentHeight: column.implicitHeight
        clip: true

        Column {
            id: column
            width: parent.width
            spacing: Units.mm(1.5)

            Repeater {
                model: page.tracks.tracks
                Rectangle {
                    id: row
                    required property var modelData
                    objectName: "trackRow"
                    width: column.width
                    height: Units.mm(17)
                    radius: Units.mm(1.5)
                    color: Theme.slotBackground
                    border.color: Theme.buttonBorder
                    border.width: 1

                    Column {
                        anchors { left: parent.left; leftMargin: Units.mm(3); right: toggle.left; rightMargin: Units.mm(2); verticalCenter: parent.verticalCenter }
                        Label {
                            width: parent.width
                            text: row.modelData.name + (row.modelData.active ? " (recording)" : "")
                            color: Theme.slotText
                            font.pixelSize: Units.mm(4.5)
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Label {
                            width: parent.width
                            text: page.durationText(row.modelData.durationS) + ", " + page.nmText(row.modelData.distanceM)
                            color: Theme.slotLabel
                            font.pixelSize: Units.mm(4)
                            elide: Text.ElideRight
                        }
                    }
                    BigButton {
                        id: toggle
                        objectName: "trackToggle"
                        anchors { right: del.left; rightMargin: Units.mm(2); verticalCenter: parent.verticalCenter }
                        width: Units.mm(22)
                        text: row.modelData.visible ? "Hide" : "Show"
                        onClicked: page.tracks.setVisible(row.modelData.id, !row.modelData.visible)
                    }
                    BigButton {
                        id: del
                        objectName: "trackDelete"
                        anchors { right: parent.right; rightMargin: Units.mm(2); verticalCenter: parent.verticalCenter }
                        width: Units.mm(24)
                        text: "Delete"
                        enabled: !row.modelData.active
                        onClicked: {
                            page.pendingId = row.modelData.id
                            page.pendingName = row.modelData.name
                            confirm.visible = true
                        }
                    }
                }
            }
        }
    }

    // The delete confirm: covers the page while open.
    Rectangle {
        id: confirm
        objectName: "confirmDelete"
        anchors.fill: parent
        visible: false
        color: Theme.background

        MouseArea { anchors.fill: parent } // swallow touches

        Column {
            anchors.centerIn: parent
            spacing: Units.mm(4)
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Delete track " + page.pendingName + "?"
                color: Theme.text
                font.pixelSize: Units.mm(5)
                font.bold: true
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Units.mm(4)
                BigButton {
                    objectName: "confirmNo"
                    width: Units.mm(35)
                    text: "Cancel"
                    onClicked: confirm.visible = false
                }
                BigButton {
                    objectName: "confirmYes"
                    width: Units.mm(35)
                    text: "Delete"
                    onClicked: {
                        page.tracks.remove(page.pendingId)
                        confirm.visible = false
                    }
                }
            }
        }
    }
}
