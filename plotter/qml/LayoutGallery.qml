import QtQuick
import QtQuick.Controls.Basic

// The layout gallery of the Setup sheet: the whole page (left of the tab bar strip), every cell
// layout as a landscape (16:10) thumbnail at least 12 mm tall in Layouts.gallery() order, scrolling,
// the draft's highlighted. A tap sets the draft's layout and closes it; so does Close, changing nothing.
Rectangle {
    id: gallery
    required property var draft     // ViewDraft
    property real rightInset: 0
    readonly property var layouts: Layouts.gallery()
    readonly property real thumbH: Units.mm(14)
    readonly property real pad: Units.mm(1.5)
    // Columns that fit at least a thumbnail wide; the thumbnails then stretch to fill the row.
    readonly property real gap: Units.mm(2)
    readonly property real minThumbW: thumbH * 1.6 + 2 * pad
    readonly property int columns: Math.max(1, Math.floor((grid.width + gap) / (minThumbW + gap)))
    // The 0.01 keeps float rounding from wrapping the last thumbnail of a row.
    readonly property real thumbW: (grid.width - (columns - 1) * gap) / columns - 0.01

    objectName: "layoutGallery"
    anchors.fill: parent
    visible: false
    color: Theme.background

    // Swallows taps on the page, so nothing under it reacts.
    MouseArea { anchors.fill: parent }

    Label {
        anchors { left: parent.left; verticalCenter: close.verticalCenter; leftMargin: Units.mm(3) }
        text: "Layout"
        color: Theme.text
        font.pixelSize: Units.mm(5)
        font.bold: true
    }
    BigButton {
        id: close
        objectName: "galleryClose"
        anchors { top: parent.top; right: parent.right; margins: Units.mm(2); rightMargin: Units.mm(2) + gallery.rightInset }
        width: Math.max(implicitWidth, Units.mm(25))
        text: "Close"
        onClicked: gallery.visible = false
    }

    Flickable {
        objectName: "galleryScroller"
        anchors {
            top: close.bottom; left: parent.left; right: parent.right; bottom: parent.bottom
            margins: Units.mm(2); rightMargin: Units.mm(2) + gallery.rightInset
        }
        contentWidth: width
        contentHeight: grid.implicitHeight
        clip: true

        Flow {
            id: grid
            width: parent.width
            spacing: gallery.gap
            Repeater {
                model: gallery.layouts
                BigButton {
                    id: choice
                    required property var modelData
                    objectName: "layout-" + modelData.key
                    padding: gallery.pad
                    width: gallery.thumbW
                    height: (width - 2 * gallery.pad) / 1.6 + 2 * gallery.pad
                    highlighted: modelData.key === gallery.draft.layout
                    onClicked: {
                        gallery.draft.layout = modelData.key
                        gallery.visible = false
                    }
                    contentItem: Item {
                        LayoutThumb {
                            anchors.centerIn: parent
                            width: choice.width - 2 * gallery.pad
                            height: width / 1.6
                            rects: choice.modelData.rects
                            highlighted: choice.highlighted
                        }
                    }
                }
            }
        }
    }
}
