import QtQuick
import QtQuick.Controls.Basic

// Full-height legend of what the shown view draws (ChartController.legendCategories): one header
// per category (title, row count, chevron) that a tap opens or closes; all start closed and the
// open ones are remembered (Settings.legendOpenIds, written through openIdsRequested). Each row
// shows the chart's own symbol (sprite or overlay image from the "legend" image provider, a fill
// swatch, a line, a sample text or a seabed abbreviation) beside its label and note. Depth band
// notes read in the user's depth unit. Scroll only (no keyboard on the boat). An in-page item, not
// a Popup, so the touch lock stays above.
Rectangle {
    id: sheet
    objectName: "legendSheet"
    property var categories: []      // [{id, title, rows, needsPack}], Legend.h
    property var openIds: []         // ids of the open categories
    property string palette: "day"   // the overlay images' palette
    property string depthUnit: "ft"
    property real shallowM: 0
    property real safetyM: 0
    property real deepM: 0
    // Where the row images come from; empty shows no images (the tests).
    property string imageBase: "image://legend/"
    signal closed()
    signal openIdsRequested(var ids)

    readonly property real metresPerUnit: depthUnit === "m" ? 1 : depthUnit === "fm" ? 1.8288 : 0.3048

    // A depth as SettingsPage.depthText shows it, without the unit: whole feet, one decimal otherwise.
    function depthNumber(m) {
        const v = m / metresPerUnit
        return depthUnit === "ft" ? String(Math.round(v)) : v.toFixed(1)
    }
    // A band end ("0", "shallow", "safety", "deep" on nav, meters on fish) in meters.
    function bandMeters(end) {
        return end === "shallow" ? shallowM : end === "safety" ? safetyM : end === "deep" ? deepM : Number(end)
    }
    // The row's note, a depth band's range first: "6 to 10 ft", "deeper than 30 ft".
    function noteFor(row) {
        let depth = ""
        if (row.depthFrom !== undefined && row.depthFrom !== "") {
            const from = depthNumber(bandMeters(row.depthFrom))
            depth = row.depthTo !== undefined && row.depthTo !== ""
                    ? from + " to " + depthNumber(bandMeters(row.depthTo)) + " " + depthUnit
                    : "deeper than " + from + " " + depthUnit
        }
        const note = row.note || ""
        return depth && note ? depth + ". " + note : depth || note
    }
    function toggle(id) {
        const ids = (openIds || []).slice()
        const i = ids.indexOf(id)
        if (i >= 0) ids.splice(i, 1)
        else ids.push(id)
        openIdsRequested(ids)
    }
    function imageSource(row) {
        if (imageBase === "" || !row.sprite) return ""
        if (row.kind === "overlay") return imageBase + "overlay/" + row.sprite + "/" + palette
        return imageBase + "sprite/" + row.sprite + "/" + (row.tint ? row.tint.replace("#", "") : "none")
    }

    color: Theme.background
    z: 10
    // Swallow touches so the chart underneath does not pan.
    MouseArea { anchors.fill: parent; onWheel: (w) => w.accepted = true }

    Label {
        id: heading
        objectName: "legendTitle"
        anchors { left: parent.left; top: parent.top; margins: Units.mm(3) }
        height: closeButton.height
        verticalAlignment: Text.AlignVCenter
        text: "Legend"
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
        contentHeight: column.height
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: column
            width: flick.width
            Repeater {
                model: sheet.categories
                Column {
                    id: category
                    required property var modelData
                    readonly property bool open: (sheet.openIds || []).indexOf(modelData.id) >= 0
                    width: column.width

                    Rectangle {
                        objectName: "legendHeader-" + category.modelData.id
                        readonly property string text: category.modelData.title + " (" + category.modelData.rows.length + ")"
                        width: parent.width
                        height: Math.max(Units.mm(12), headerLabel.implicitHeight + Units.mm(3))
                        color: headerTap.pressed ? Theme.buttonDown : Theme.button
                        Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.buttonBorder }
                        Label {
                            id: chevron
                            x: Units.mm(4); width: Units.mm(6)
                            anchors.verticalCenter: parent.verticalCenter
                            horizontalAlignment: Text.AlignHCenter
                            text: "›"
                            rotation: category.open ? 90 : 0
                            color: Theme.buttonText
                            font.pixelSize: Units.mm(6)
                            font.bold: true
                        }
                        Label {
                            id: headerLabel
                            anchors { left: chevron.right; right: parent.right; leftMargin: Units.mm(2); rightMargin: Units.mm(4); verticalCenter: parent.verticalCenter }
                            text: parent.text
                            color: Theme.buttonText
                            font.pixelSize: Units.mm(4.5)
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        MouseArea { id: headerTap; anchors.fill: parent; onClicked: sheet.toggle(category.modelData.id) }
                    }

                    Label {
                        objectName: "legendNeedsPack-" + category.modelData.id
                        visible: category.open && category.modelData.needsPack
                        x: Units.mm(12); width: parent.width - x - Units.mm(4)
                        height: visible ? Units.mm(12) : 0
                        verticalAlignment: Text.AlignVCenter
                        text: "Needs a charts pack"
                        color: Theme.disabledText
                        font.pixelSize: Units.mm(4.5)
                    }

                    // Rows exist only while their category is open (no images asked for while closed).
                    Repeater {
                        model: category.open ? category.modelData.rows : []
                        Rectangle {
                            id: row
                            required property var modelData
                            objectName: "legendRow"
                            readonly property string label: modelData.label
                            readonly property string noteText: sheet.noteFor(modelData)
                            readonly property string sampleText: modelData.kind === "seabed" || modelData.kind === "text" ? modelData.text : ""
                            width: category.width
                            height: Math.max(Units.mm(12), Math.max(sample.height, labels.implicitHeight) + Units.mm(3))
                            color: "transparent"
                            Rectangle { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } height: 1; color: Theme.buttonBorder }

                            // The symbol, centered in a fixed column.
                            Item {
                                id: sample
                                x: Units.mm(4); width: Units.mm(25)
                                height: Math.max(Units.mm(6), symbol.item ? symbol.item.height : 0)
                                anchors.verticalCenter: parent.verticalCenter
                                Loader {
                                    id: symbol
                                    anchors.centerIn: parent
                                    sourceComponent: row.modelData.kind === "swatch" ? swatchComp
                                                   : row.modelData.kind === "line" ? lineComp
                                                   : row.modelData.kind === "text" || row.modelData.kind === "seabed" ? textComp
                                                   : sheet.imageSource(row.modelData) !== "" ? imageComp : null
                                }
                                Component {
                                    id: imageComp
                                    Image {
                                        objectName: "legendImage"
                                        source: sheet.imageSource(row.modelData)
                                        // Map size: the provider gives the logical size, scaled by the layer's icon-size.
                                        width: implicitWidth * (row.modelData.iconSize || 1)
                                        height: implicitHeight * (row.modelData.iconSize || 1)
                                        cache: false // the sheet behind a sprite id changes with the view
                                        smooth: true
                                    }
                                }
                                Component {
                                    id: swatchComp
                                    Rectangle {
                                        width: Units.mm(12); height: Units.mm(7)
                                        color: row.modelData.color || "transparent"
                                        border.color: Theme.buttonBorder
                                    }
                                }
                                Component {
                                    id: lineComp
                                    Item {
                                        id: line
                                        readonly property real w: Math.max(1, row.modelData.width || 1)
                                        // On-segments of the dash pattern (in line widths, as MapLibre) along the sample.
                                        readonly property var segments: {
                                            const len = width, d = row.modelData.dash || []
                                            const total = d.reduce((a, b) => a + b, 0) * w
                                            if (d.length < 2 || total <= 0) return [{ x: 0, w: len }]
                                            const out = []
                                            let x = 0, i = 0
                                            while (x < len) {
                                                const seg = d[i % d.length] * w
                                                if (i % 2 === 0) out.push({ x: x, w: Math.min(seg, len - x) })
                                                x += seg
                                                ++i
                                            }
                                            return out
                                        }
                                        width: Units.mm(12); height: w
                                        Repeater {
                                            model: line.segments
                                            Rectangle {
                                                required property var modelData
                                                x: modelData.x; width: modelData.w; height: line.w
                                                color: row.modelData.color || Theme.text
                                            }
                                        }
                                    }
                                }
                                Component {
                                    id: textComp
                                    Label {
                                        text: row.modelData.text
                                        color: row.modelData.kind === "text" && row.modelData.color ? row.modelData.color : Theme.text
                                        font.pixelSize: Units.mm(row.modelData.kind === "seabed" ? 5 : 4)
                                        font.bold: row.modelData.kind === "seabed"
                                    }
                                }
                            }
                            Column {
                                id: labels
                                anchors { left: sample.right; right: parent.right; leftMargin: Units.mm(3); rightMargin: Units.mm(4); verticalCenter: parent.verticalCenter }
                                Label {
                                    objectName: "legendLabel"
                                    width: parent.width
                                    text: row.label
                                    color: Theme.text
                                    font.pixelSize: Units.mm(4.5)
                                    wrapMode: Text.WordWrap
                                }
                                Label {
                                    objectName: "legendNote"
                                    width: parent.width
                                    visible: text !== ""
                                    text: row.noteText
                                    color: Theme.disabledText
                                    font.pixelSize: Units.mm(4)
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
