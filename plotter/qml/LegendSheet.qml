import QtQuick
import QtQuick.Controls.Basic

// Full-height seabed legend: one row per legend.json entry (abbreviation bold, meaning, kind).
// Scroll only (no keyboard on the boat). An in-page item, not a Popup, so the touch lock stays above.
Rectangle {
    id: sheet
    objectName: "legendSheet"
    property var entries: []   // [{abbr, meaning, kind}]
    signal closed()

    color: Theme.background
    z: 10
    // Swallow touches so the chart underneath does not pan.
    MouseArea { anchors.fill: parent; onWheel: (w) => w.accepted = true }

    Label {
        id: heading
        anchors { left: parent.left; top: parent.top; margins: Units.mm(3) }
        height: closeButton.height
        verticalAlignment: Text.AlignVCenter
        text: "Seabed legend"
        color: Theme.text
        font.pixelSize: Units.mm(5)
        font.bold: true
    }
    BigButton {
        id: closeButton
        objectName: "legendCloseButton"
        anchors { right: parent.right; top: parent.top; margins: Units.mm(3) }
        text: "Close"
        onClicked: sheet.closed()
    }

    Flickable {
        id: flick
        anchors { left: parent.left; right: parent.right; top: closeButton.bottom; bottom: parent.bottom; topMargin: Units.mm(3) }
        clip: true
        contentWidth: width
        contentHeight: rows.height
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: rows
            width: flick.width
            Repeater {
                model: sheet.entries
                Rectangle {
                    id: row
                    required property var modelData
                    objectName: "legendRow"
                    width: rows.width
                    height: Math.max(Units.mm(12), Math.max(abbrLabel.implicitHeight, meaningLabel.implicitHeight) + Units.mm(3))
                    color: "transparent"
                    Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.buttonBorder }
                    Label {
                        id: abbrLabel
                        x: Units.mm(4); width: Units.mm(25)
                        anchors.verticalCenter: parent.verticalCenter
                        text: row.modelData.abbr
                        color: Theme.text
                        font.pixelSize: Units.mm(5)
                        font.bold: true
                    }
                    Label {
                        id: meaningLabel
                        anchors { left: abbrLabel.right; right: kindLabel.left; verticalCenter: parent.verticalCenter; rightMargin: Units.mm(3) }
                        text: row.modelData.meaning
                        color: Theme.text
                        font.pixelSize: Units.mm(4.5)
                        wrapMode: Text.WordWrap
                    }
                    Label {
                        id: kindLabel
                        anchors { right: parent.right; rightMargin: Units.mm(4); verticalCenter: parent.verticalCenter }
                        width: Units.mm(30)
                        horizontalAlignment: Text.AlignRight
                        text: row.modelData.kind
                        color: Theme.disabledText
                        font.pixelSize: Units.mm(4)
                    }
                }
            }
        }
    }
}
