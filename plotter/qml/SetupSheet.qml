import QtQuick
import QtQuick.Controls.Basic

// The Setup sheet of the view editor (spec 6.7): a pop-out the full height of the page at its left,
// in the slot sheet's look, scrolling: Name and Short name (each opens the keyboard), the icon grid
// (4 across), Chart (Nav, Fish or None), Layout (with no chart; opens the layout gallery),
// Favourite, Delete view (asks first; not the last view). Every pick writes straight into the draft,
// so the view beside the sheet follows at once (Cancel in the editor drops it all). Done closes the
// sheet only. The rest of the page is covered: a tap beside the sheet does nothing.
Item {
    id: sheet
    required property var draft     // ViewDraft
    required property var views     // ViewsModel
    property real rightInset: 0     // the tab bar strip over the page's right edge
    property bool confirming: false // Delete asked "Delete <name>?"
    property string keyboardField: "" // name or short: what the keyboard edits
    signal deleteRequested()
    signal closed()

    objectName: "setupSheet"
    anchors.fill: parent
    visible: false

    // A favourite with no tab: the stored view's own answer, or, while the draft's favourite is not
    // stored yet, whether the bar is already full.
    readonly property bool offTabBar: {
        void views.tabViews // onTabBar() is a call: tabViews changes whenever its answer can
        if (!draft.favourite) return false
        return views.viewJson(draft.id).favourite === true ? !views.onTabBar(draft.id)
                                                           : views.tabViews.length >= views.favouriteCapacity
    }

    onVisibleChanged: {
        confirming = false
        keyboard.visible = false
        gallery.visible = false
        scroller.contentY = 0
    }

    function editText(field) {
        keyboardField = field
        if (field === "name") keyboard.open("Name", draft.name, 24)
        else keyboard.open("Short name", draft.shortName, 6)
    }

    // Taps beside the sheet do nothing.
    MouseArea { anchors.fill: parent }

    Rectangle {
        id: panel
        objectName: "setupPanel"
        width: Math.min(Units.mm(110), sheet.width - sheet.rightInset)
        height: sheet.height
        color: Theme.background
        border.color: Theme.buttonBorder
        border.width: Math.max(2, Units.mm(0.5))

        MouseArea { anchors.fill: parent }

        Label {
            anchors { left: parent.left; verticalCenter: done.verticalCenter; leftMargin: Units.mm(3) }
            text: "Setup"
            color: Theme.text
            font.pixelSize: Units.mm(5)
            font.bold: true
        }
        BigButton {
            id: done
            objectName: "setupDone"
            anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
            width: Math.max(implicitWidth, Units.mm(25))
            text: "Done"
            onClicked: sheet.closed()
        }

        Flickable {
            id: scroller
            objectName: "setupScroller"
            anchors { top: done.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(2) }
            contentWidth: width
            contentHeight: column.implicitHeight
            clip: true

            Column {
                id: column
                width: scroller.width
                spacing: Units.mm(1.5)

                component Heading: Label {
                    color: Theme.text
                    font.pixelSize: Units.mm(3.5)
                    height: Units.mm(5)
                    verticalAlignment: Text.AlignBottom
                }
                component RowButton: BigButton {
                    id: rowButton
                    width: column.width
                    contentItem: Label {
                        text: rowButton.text
                        font: rowButton.font
                        color: rowButton.enabled ? Theme.buttonText : Theme.disabledText
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }

                RowButton {
                    objectName: "row-name"
                    text: "Name: " + sheet.draft.name
                    onClicked: sheet.editText("name")
                }
                RowButton {
                    objectName: "row-short"
                    text: "Short name: " + sheet.draft.shortName
                    onClicked: sheet.editText("short")
                }

                Heading { text: "Icon" }
                Grid {
                    id: icons
                    columns: 4
                    spacing: Units.mm(1.5)
                    readonly property real cell: (column.width - 3 * spacing) / 4
                    Repeater {
                        model: Icons.names()
                        BigButton {
                            required property string modelData
                            objectName: "icon-" + modelData
                            width: icons.cell
                            highlighted: sheet.draft.icon === modelData
                            onClicked: sheet.draft.icon = modelData
                            contentItem: Item {
                                Icon {
                                    anchors.centerIn: parent
                                    width: Units.mm(7)
                                    height: Units.mm(7)
                                    name: modelData
                                }
                            }
                        }
                    }
                }

                Heading { text: "Chart" }
                Row {
                    id: charts
                    spacing: Units.mm(1.5)
                    readonly property real cell: (column.width - 2 * spacing) / 3
                    Repeater {
                        model: [["nav", "Nav"], ["fish", "Fish"], ["none", "None"]]
                        BigButton {
                            required property var modelData
                            objectName: "chart-" + modelData[0]
                            width: charts.cell
                            text: modelData[1]
                            highlighted: sheet.draft.chart === modelData[0]
                            onClicked: sheet.draft.chart = modelData[0]
                        }
                    }
                }
                RowButton {
                    objectName: "row-layout"
                    visible: sheet.draft.chart === "none"
                    text: "Layout"
                    onClicked: gallery.visible = true
                }

                Heading { text: "Tab bar" }
                RowButton {
                    objectName: "row-favourite"
                    text: "Favourite: " + (sheet.draft.favourite ? "On" : "Off")
                    onClicked: sheet.draft.favourite = !sheet.draft.favourite
                }
                Label {
                    objectName: "favouriteNote"
                    visible: sheet.offTabBar
                    text: "Not on tab bar (full)"
                    color: Theme.text
                    font.pixelSize: Units.mm(3.5)
                }

                Item { width: 1; height: Units.mm(3) }
                RowButton {
                    objectName: "row-delete"
                    visible: !sheet.confirming
                    enabled: sheet.views.count > 1
                    text: enabled ? "Delete view" : "Can't delete the last view"
                    onClicked: sheet.confirming = true
                }
                Label {
                    objectName: "setupDeleteQuestion"
                    visible: sheet.confirming
                    width: column.width
                    text: "Delete " + sheet.draft.name + "?"
                    color: Theme.text
                    font.pixelSize: Units.mm(5)
                    font.bold: true
                    elide: Text.ElideRight
                }
                Row {
                    visible: sheet.confirming
                    spacing: Units.mm(1.5)
                    BigButton {
                        objectName: "setupDeleteYes"
                        width: (column.width - parent.spacing) / 2
                        text: "Delete"
                        onClicked: sheet.deleteRequested()
                    }
                    BigButton {
                        objectName: "setupKeep"
                        width: (column.width - parent.spacing) / 2
                        text: "Keep"
                        onClicked: sheet.confirming = false
                    }
                }
            }
        }
    }

    Keyboard {
        id: keyboard
        rightInset: sheet.rightInset
        onAccepted: (text) => {
            if (sheet.keyboardField === "name") sheet.draft.name = text
            else sheet.draft.shortName = text
        }
    }
    LayoutGallery {
        id: gallery
        draft: sheet.draft
        rightInset: sheet.rightInset
    }
}
