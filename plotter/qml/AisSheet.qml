import QtQuick
import QtQuick.Controls.Basic

// Details of the tapped AIS target: name, MMSI, class, SOG, COG, range, bearing, position age.
// An in-page item, not a Popup, so the touch lock stays above. `info` is ChartController::aisSelection;
// the sheet shows while it is non-empty, and closes (the controller clears it) through Close or when
// the target is gone.
Rectangle {
    id: sheet
    objectName: "aisSheet"
    property var info: ({})
    signal closed()

    readonly property var rows: [
        { label: "Name", value: info.name },
        { label: "MMSI", value: info.mmsi },
        { label: "Class", value: info.cls },
        { label: "SOG (kn)", value: info.sog },
        { label: "COG (deg)", value: info.cog },
        { label: "Range (nm)", value: info.range },
        { label: "Bearing (deg)", value: info.bearing },
        { label: "Position age", value: info.posAge }
    ]

    visible: info.mmsi !== undefined
    color: Theme.background
    border.color: Theme.buttonBorder
    radius: Units.mm(1.5)
    z: 10
    width: Units.mm(90)
    height: column.implicitHeight + Units.mm(6)
    // Swallow touches so the chart underneath does not pan or pick another target.
    MouseArea { anchors.fill: parent; onWheel: (w) => w.accepted = true }

    Column {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Units.mm(3) }
        spacing: Units.mm(1)
        Repeater {
            model: sheet.rows
            Item {
                id: row
                required property var modelData
                width: column.width
                height: Units.mm(7)
                Label {
                    anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                    text: row.modelData.label
                    color: Theme.disabledText
                    font.pixelSize: Units.mm(4)
                }
                Label {
                    objectName: "aisValue"
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    text: row.modelData.value === undefined ? "--" : row.modelData.value
                    color: Theme.text
                    font.pixelSize: Units.mm(5)
                    font.bold: true
                }
            }
        }
        Item {
            width: column.width
            height: closeButton.height
            BigButton {
                id: closeButton
                objectName: "aisCloseButton"
                anchors.right: parent.right
                text: "Close"
                onClicked: sheet.closed()
            }
        }
    }
}
