import QtQuick
import QtQuick.Controls.Basic

// Every tappable control in the app is a BigButton or derives from it: at least 12 mm both ways
// (wet fingers), in the Theme colours. `highlighted` marks the current choice in a list.
Button {
    id: control
    readonly property bool isBigButton: true
    property real minimumSize: Units.mm(12)

    implicitWidth: Math.max(minimumSize, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(minimumSize, implicitContentHeight + topPadding + bottomPadding)
    padding: Units.mm(2)
    font.pixelSize: Units.mm(4)

    contentItem: Label {
        text: control.text
        font: control.font
        color: control.enabled ? Theme.buttonText : Theme.disabledText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: Units.mm(1.5)
        color: !control.enabled ? Theme.disabledButton
             : control.down ? Theme.buttonDown
             : control.highlighted ? Theme.buttonSelected : Theme.button
        border.color: Theme.buttonBorder
        border.width: control.highlighted ? Math.max(2, Units.mm(0.6)) : 1
    }
}
