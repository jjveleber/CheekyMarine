import QtQuick
import QtQuick.Controls.Basic

// Details of the tapped AIS target: name, MMSI, class, SOG, COG, range, bearing, position age.
// An in-page item, not a Popup, so the touch lock stays above. `info` is ChartController::aisSelection;
// the sheet shows while it is non-empty, and closes (the controller clears it) through Close or when
// the target is gone. It lives in `freeRect` (the chart page's free area between the corner slots):
// the rows are "label: value" lines that wrap, and when they do not all fit above the footer they
// are laid in pages that the footer's tap buttons step through.
Rectangle {
    id: sheet
    objectName: "aisSheet"
    property var info: ({})
    property rect freeRect: Qt.rect(0, 0, Units.mm(90), Units.mm(200))
    property int page: 0
    readonly property int pageCount: pageStarts.length
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

    readonly property real pad: Units.mm(3)
    readonly property real gap: Units.mm(1)
    readonly property real footerHeight: Units.mm(12)
    // The row heights at the current width, whether or not the row is on the shown page.
    property var heights: []
    readonly property real avail: Math.max(0, freeRect.height - 2 * pad - footerHeight - gap)
    // The index of the first row of each page: consecutive rows that fit above the footer (a row
    // taller than that gets a page of its own).
    readonly property var pageStarts: {
        const starts = [0]
        let used = 0
        for (let i = 0; i < heights.length; ++i) {
            const need = (used > 0 ? gap : 0) + heights[i]
            if (used > 0 && used + need > avail) {
                starts.push(i)
                used = heights[i]
            } else {
                used += need
            }
        }
        return starts
    }
    onPageCountChanged: if (page >= pageCount) page = pageCount - 1
    property var shownMmsi
    onInfoChanged: {
        if (info.mmsi !== shownMmsi) {
            shownMmsi = info.mmsi
            page = 0
        }
    }
    function measure() {
        const h = []
        for (let i = 0; i < rowRepeater.count; ++i) {
            const it = rowRepeater.itemAt(i)
            h.push(it ? it.implicitHeight : 0)
        }
        if (h.join() !== heights.join()) heights = h
    }

    visible: info.mmsi !== undefined
    color: Theme.background
    border.color: Theme.buttonBorder
    radius: Units.mm(1.5)
    z: 10
    width: Math.max(Math.min(freeRect.width, Units.mm(90)), Units.mm(60))
    height: Math.min(column.implicitHeight + 2 * pad, freeRect.height)
    // Swallow touches so the chart underneath does not pan or pick another target.
    MouseArea { anchors.fill: parent; onWheel: (w) => w.accepted = true }

    Column {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: sheet.pad }
        spacing: sheet.gap
        Repeater {
            id: rowRepeater
            model: sheet.rows
            onItemAdded: sheet.measure()
            Label {
                id: row
                required property var modelData
                required property int index
                objectName: "aisValue"
                width: column.width
                visible: index >= sheet.pageStarts[Math.min(sheet.page, sheet.pageCount - 1)]
                         && (sheet.page + 1 >= sheet.pageCount || index < sheet.pageStarts[sheet.page + 1])
                text: modelData.label + ": " + (modelData.value === undefined ? "--" : modelData.value)
                wrapMode: Text.WordWrap
                color: Theme.text
                font.pixelSize: Units.mm(4)
                onImplicitHeightChanged: sheet.measure()
            }
        }
        Item {
            width: column.width
            height: sheet.footerHeight
            Row {
                spacing: Units.mm(1)
                visible: sheet.pageCount > 1
                BigButton {
                    objectName: "aisPrev"
                    text: "<"
                    enabled: sheet.page > 0
                    onClicked: sheet.page = Math.max(0, sheet.page - 1)
                }
                Label {
                    objectName: "aisPageLabel"
                    anchors.verticalCenter: parent.verticalCenter
                    text: (sheet.page + 1) + " of " + sheet.pageCount
                    color: Theme.text
                    font.pixelSize: Units.mm(3.5)
                }
                BigButton {
                    objectName: "aisNext"
                    text: ">"
                    enabled: sheet.page < sheet.pageCount - 1
                    onClicked: sheet.page = Math.min(sheet.pageCount - 1, sheet.page + 1)
                }
            }
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
