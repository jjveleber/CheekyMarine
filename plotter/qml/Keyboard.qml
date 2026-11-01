import QtQuick
import QtQuick.Controls.Basic

// The on-screen keyboard: a full-page overlay with the typed text and its count over the key rows.
// open() shows it; Done emits accepted(text), Cancel emits cancelled() and puts the old text back;
// both close it. shift is on when opened with empty text, turns off after one letter, and toggles by
// its key. Typing past maxChars does nothing, and Done needs some text.
Rectangle {
    id: keyboard
    property string title: ""
    property string text: ""
    property int maxChars: 24
    property bool shift: false
    property real rightInset: 0
    property string _old: ""
    signal accepted(string text)
    signal cancelled()

    objectName: "keyboard"
    anchors.fill: parent
    visible: false
    color: Theme.background

    function open(title, text, maxChars) {
        keyboard.title = title
        keyboard.maxChars = maxChars
        keyboard.text = text
        _old = text
        shift = text.length === 0
        visible = true
    }
    function type(ch) {
        if (text.length >= maxChars) return
        text += ch
    }

    // Swallows taps on the page, so nothing under it reacts.
    MouseArea { anchors.fill: parent }

    component Key: BigButton {
        property string label: ""
        readonly property bool letter: label.length === 1 && label >= "A" && label <= "Z"
        objectName: "key-" + label
        minimumSize: Units.mm(12)
        padding: 0
        text: letter && !keyboard.shift ? label.toLowerCase() : label
        onClicked: {
            keyboard.type(text)
            if (letter) keyboard.shift = false
        }
    }
    component KeyRow: Row {
        property string keys: ""
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Units.mm(1)
        Repeater {
            model: keys.split("")
            Key { required property string modelData; label: modelData; width: Units.mm(12) }
        }
    }

    Column {
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: -keyboard.rightInset / 2
        spacing: Units.mm(1)

        Label {
            text: keyboard.title
            color: Theme.text
            font.pixelSize: Units.mm(3.5)
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Rectangle {
            objectName: "keyboardText"
            width: Units.mm(129)
            height: Units.mm(12)
            color: Theme.button
            border.color: Theme.buttonBorder
            border.width: 1
            radius: Units.mm(1.5)
            Label {
                anchors { left: parent.left; right: count.left; verticalCenter: parent.verticalCenter; margins: Units.mm(2) }
                text: keyboard.text
                color: Theme.buttonText
                font.pixelSize: Units.mm(5)
                elide: Text.ElideLeft
            }
            Label {
                id: count
                objectName: "keyboardCount"
                anchors { right: parent.right; verticalCenter: parent.verticalCenter; margins: Units.mm(2) }
                text: keyboard.text.length + "/" + keyboard.maxChars
                color: Theme.text
                font.pixelSize: Units.mm(3.5)
            }
        }

        KeyRow { keys: "1234567890" }
        KeyRow { keys: "QWERTYUIOP" }
        KeyRow { keys: "ASDFGHJKL" }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Units.mm(1)
            BigButton {
                objectName: "key-shift"
                width: Units.mm(20)
                padding: 0
                text: "Shift"
                highlighted: keyboard.shift
                onClicked: keyboard.shift = !keyboard.shift
            }
            Repeater {
                model: "ZXCVBNM".split("")
                Key { required property string modelData; label: modelData; width: Units.mm(12) }
            }
            BigButton {
                objectName: "key-backspace"
                width: Units.mm(20)
                padding: 0
                text: "Back"
                onClicked: keyboard.text = keyboard.text.slice(0, -1)
            }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Units.mm(1)
            BigButton {
                objectName: "key-cancel"
                width: Units.mm(30)
                padding: 0
                text: "Cancel"
                onClicked: {
                    keyboard.text = keyboard._old
                    keyboard.visible = false
                    keyboard.cancelled()
                }
            }
            BigButton {
                objectName: "key-space"
                width: Units.mm(65)
                padding: 0
                text: "Space"
                onClicked: keyboard.type(" ")
            }
            BigButton {
                objectName: "key-done"
                width: Units.mm(30)
                padding: 0
                text: "Done"
                enabled: keyboard.text.length > 0
                onClicked: {
                    keyboard.visible = false
                    keyboard.accepted(keyboard.text)
                }
            }
        }
    }
}
