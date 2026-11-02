import QtQuick

// A cell layout drawn small: each cell of `rects` (fractions of the page) a rounded rectangle
// outlined in the button text colour, 1 px apart; filled in the selected colour when highlighted.
Item {
    id: thumb
    property var rects: []
    property bool highlighted: false
    readonly property real gap: 1

    objectName: "layoutThumb"

    Repeater {
        model: thumb.rects
        Rectangle {
            required property var modelData
            x: thumb.gap + modelData.x * (thumb.width - thumb.gap)
            y: thumb.gap + modelData.y * (thumb.height - thumb.gap)
            width: Math.max(0, modelData.w * (thumb.width - thumb.gap) - thumb.gap)
            height: Math.max(0, modelData.h * (thumb.height - thumb.gap) - thumb.gap)
            radius: 2
            color: thumb.highlighted ? Theme.buttonSelected : Theme.button
            border.color: Theme.buttonText
            border.width: 1
        }
    }
}
