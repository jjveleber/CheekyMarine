import QtQuick
import QtQuick.Controls.Basic

// The slot sheet of the view editor: half the page, in the half away from the slot (atTop when the
// slot is in the bottom half). Show On or Off, the field, the size: - and + step 0.5 mm a tap and,
// held, move it 2 mm per second after 400 ms, both within [6, maxMm]. Every change emits changed;
// the editor applies it and sets sizeMm (and maxMm) to what it applied. Done emits closed.
Rectangle {
    id: sheet
    property string slotId: ""
    property bool on: true
    property string field: "depth"
    property real sizeMm: 14
    property real maxMm: 6
    property var fieldChoices: []
    property bool atTop: false
    property real rightInset: 0
    signal changed(bool on, string field, real sizeMm)
    signal closed()

    objectName: "slotSheet"
    visible: false
    y: atTop ? 0 : parent.height / 2
    width: parent.width - rightInset
    height: parent.height / 2
    color: Theme.background
    border.color: Theme.buttonBorder
    border.width: Math.max(2, Units.mm(0.5))

    onVisibleChanged: scroller.contentY = 0

    function setSize(mm) { changed(on, field, Math.max(6, Math.min(maxMm, mm))) }

    // Swallows taps on the sheet, so nothing under it reacts.
    MouseArea { anchors.fill: parent }

    BigButton {
        id: done
        objectName: "sheetDone"
        anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Done"
        onClicked: sheet.closed()
    }

    // Left of Done, so nothing runs under it: Show over Size, then Field, which wraps under them when
    // the sheet is narrow; the sheet scrolls only when it is short (the panel diagonal goes from 7 to
    // 15 in), so a thumb that drifts on a held + is not a scroll.
    Flickable {
        id: scroller
        objectName: "slotSheetScroller"
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom; right: done.left; margins: Units.mm(2) }
        contentWidth: width
        contentHeight: groups.implicitHeight
        flickableDirection: Flickable.AutoFlickIfNeeded
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Flow {
            id: groups
            width: scroller.width
            spacing: Units.mm(4)

            component Heading: Label {
                color: Theme.text
                font.pixelSize: Units.mm(3.5)
                height: Units.mm(5)
            }

            Column {
                spacing: Units.mm(4)
                Column {
                    spacing: Units.mm(1.5)
                    Heading { text: "Show" }
                    Row {
                        spacing: Units.mm(1.5)
                        BigButton {
                            objectName: "choice-on"
                            width: Units.mm(18)
                            text: "On"
                            highlighted: sheet.on
                            onClicked: sheet.changed(true, sheet.field, sheet.sizeMm)
                        }
                        BigButton {
                            objectName: "choice-off"
                            width: Units.mm(18)
                            text: "Off"
                            highlighted: !sheet.on
                            onClicked: sheet.changed(false, sheet.field, sheet.sizeMm)
                        }
                    }
                }
                Column {
                    spacing: Units.mm(1.5)
                    Heading { text: "Size" }
                    Row {
                        spacing: Units.mm(1.5)
                        SizeButton { objectName: "sizeMinus"; text: "−"; direction: -1 }
                        Label {
                            objectName: "sizeValue"
                            width: Units.mm(22)
                            height: Units.mm(12)
                            text: sheet.sizeMm.toFixed(1) + " mm"
                            color: Theme.text
                            font.pixelSize: Units.mm(5)
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        SizeButton { objectName: "sizePlus"; text: "+"; direction: 1 }
                    }
                }
            }

            Column {
                spacing: Units.mm(1.5)
                Heading { text: "Field" }
                Grid {
                    columns: 3
                    spacing: Units.mm(1.5)
                    Repeater {
                        model: sheet.fieldChoices
                        BigButton {
                            required property var modelData
                            objectName: "choice-field-" + modelData.name
                            width: Units.mm(30)
                            text: modelData.label
                            highlighted: sheet.field === modelData.name
                            onClicked: sheet.changed(sheet.on, modelData.name, sheet.sizeMm)
                        }
                    }
                }
            }
        }
    }

    // A tap steps 0.5 mm. Held, after 400 ms the size follows the hold at 2 mm per second from where
    // it was, by the clock (so a late tick does not lose any of it), on the 0.5 mm grid, each 125 ms
    // and on release. Sliding off the button stops it.
    component SizeButton: BigButton {
        id: button
        property int direction: 1
        property bool repeating: false
        property real base: 0
        property real since: 0
        topPadding: 0
        bottomPadding: 0
        font.pixelSize: Units.mm(8)
        function follow() { sheet.setSize(Math.round((base + direction * 2 * (Date.now() - since) / 1000) * 2) / 2) }
        onPressed: { repeating = false; delay.restart() }
        onPressedChanged: if (!pressed) { delay.stop(); repeat.stop() }
        onReleased: if (repeating) follow()
        onClicked: if (!repeating) sheet.setSize(sheet.sizeMm + direction * 0.5)
        Timer {
            id: delay
            interval: 400
            onTriggered: {
                button.repeating = true
                button.base = sheet.sizeMm
                button.since = Date.now()
                repeat.start()
            }
        }
        Timer {
            id: repeat
            interval: 125
            repeat: true
            onTriggered: button.follow()
        }
    }
}
