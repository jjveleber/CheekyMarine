import QtQuick

// A small picture of a view for its Home tile. A chart view: its on slots as boxes over the chart
// colour, each at its place and roughly its size on the page (a corner is sizeMm * 2.8 wide and
// sizeMm * 1.6 tall, as a fraction of the window in mm, capped at 0.45 and 0.3 of the thumb; bars
// run full length, the side bars between the top and bottom ones). A view with no chart: its cells
// by the layout, 2 px apart.
Rectangle {
    id: thumb
    property string chart: "nav"
    property var slots: []      // [{id, on, field, sizeMm}]
    property string layout: ""

    readonly property real pageWMm: Units.windowWidth / Units.pxPerMm
    readonly property real pageHMm: Units.windowHeight / Units.pxPerMm
    readonly property real gap: 2
    readonly property var cellRects: chart === "none" ? Layouts.rects(layout) : []

    function slotOn(id) {
        for (const s of slots) if (s.id === id) return s.on ? s : null
        return null
    }
    function fracW(s) { return Math.min(0.45, s.sizeMm * 2.8 / pageWMm) * width }
    function fracH(s) { return Math.min(0.3, s.sizeMm * 1.6 / pageHMm) * height }
    // The room the bars take at each edge.
    readonly property real topH: chart !== "none" && slotOn("Top") ? fracH(slotOn("Top")) : 0
    readonly property real bottomH: chart !== "none" && slotOn("Bottom") ? fracH(slotOn("Bottom")) : 0
    readonly property real leftW: chart !== "none" && slotOn("Left") ? fracW(slotOn("Left")) : 0
    readonly property real rightW: chart !== "none" && slotOn("Right") ? fracW(slotOn("Right")) : 0

    objectName: "viewThumb"
    color: chart === "nav" ? Theme.thumbNav : chart === "fish" ? Theme.thumbFish : Theme.background
    border.color: Theme.buttonBorder
    border.width: 1
    clip: true

    Repeater {
        model: thumb.chart !== "none" ? thumb.slots : []
        Rectangle {
            required property var modelData
            readonly property string slotId: modelData.id
            readonly property bool bar: slotId === "Top" || slotId === "Bottom" || slotId === "Left" || slotId === "Right"
            objectName: "thumbSlot"
            visible: modelData.on
            width: slotId === "Top" || slotId === "Bottom" ? thumb.width : thumb.fracW(modelData)
            height: slotId === "Left" || slotId === "Right" ? thumb.height - thumb.topH - thumb.bottomH : thumb.fracH(modelData)
            x: slotId === "Top" || slotId === "Bottom" || slotId === "Left" ? 0
             : slotId === "Right" ? thumb.width - width
             : slotId === "TL" || slotId === "BL" ? thumb.leftW + thumb.gap
             : thumb.width - thumb.rightW - thumb.gap - width
            y: slotId === "Top" ? 0
             : slotId === "Bottom" ? thumb.height - height
             : slotId === "Left" || slotId === "Right" ? thumb.topH
             : slotId === "TL" || slotId === "TR" ? thumb.topH + thumb.gap
             : thumb.height - thumb.bottomH - thumb.gap - height
            color: Theme.slotBackground
            border.color: Theme.buttonBorder
            border.width: 1
            radius: bar ? 0 : 2
        }
    }

    Repeater {
        model: thumb.cellRects
        Rectangle {
            required property var modelData
            objectName: "thumbCell"
            x: thumb.gap + modelData.x * (thumb.width - thumb.gap)
            y: thumb.gap + modelData.y * (thumb.height - thumb.gap)
            width: Math.max(0, modelData.w * (thumb.width - thumb.gap) - thumb.gap)
            height: Math.max(0, modelData.h * (thumb.height - thumb.gap) - thumb.gap)
            color: Theme.button
            border.color: Theme.buttonBorder
            border.width: 1
            radius: 2
        }
    }
}
