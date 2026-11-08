import QtQuick
import QtQuick.Controls.Basic

// A title with a value between "-" and "+" buttons. A tap steps once; held, after 400 ms it steps
// 5 times a second until release. The caller clamps in its minus and plus handlers.
Item {
    id: st
    property string title: ""
    property string value: ""
    property string valueName: ""
    readonly property string text: title + ": " + value
    signal minus()
    signal plus()
    height: Units.mm(12)

    Label {
        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
        text: st.title
        color: Theme.text
        font.pixelSize: Units.mm(4)
    }
    Row {
        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
        spacing: Units.mm(2)
        HoldButton { objectName: st.valueName + "Minus"; text: "-"; onStep: st.minus() }
        Label {
            objectName: st.valueName + "Value"
            width: Units.mm(24)
            height: Units.mm(12)
            text: st.value
            color: Theme.text
            font.pixelSize: Units.mm(4.5)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        HoldButton { objectName: st.valueName + "Plus"; text: "+"; onStep: st.plus() }
    }

    component HoldButton: BigButton {
        id: button
        property bool repeating: false
        signal step()
        width: Units.mm(14)
        onPressed: { repeating = false; delay.restart() }
        onPressedChanged: if (!pressed) { delay.stop(); repeat.stop() }
        onClicked: if (!repeating) step()
        Timer {
            id: delay
            interval: 400
            onTriggered: { button.repeating = true; button.step(); repeat.start() }
        }
        Timer {
            id: repeat
            interval: 200
            repeat: true
            onTriggered: button.step()
        }
    }
}
