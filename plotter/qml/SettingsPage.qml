import QtQuick
import QtQuick.Controls.Basic

// Every setting on big buttons, no keyboard: choice rows open a big list (a tap applies and
// closes), depth and panel diagonal rows are steppers.
Item {
    id: page
    required property QtObject settings // Settings
    signal editOverlays()
    signal showAbout()

    objectName: "settingsPage"

    readonly property string depthUnit: settings.depthUnit
    readonly property real metresPerStep: depthUnit === "m" ? 0.5 : depthUnit === "fm" ? 0.9144 : 0.3048
    readonly property real metresPerUnit: depthUnit === "m" ? 1 : depthUnit === "fm" ? 1.8288 : 0.3048

    property string depthError: ""

    function choiceLabel(choices, value) {
        for (const c of choices) if (c.value === value) return c.label
        return String(value)
    }
    readonly property var depthUnits: [{ value: "ft", label: "Feet" }, { value: "m", label: "Metres" }, { value: "fm", label: "Fathoms" }]
    readonly property var speedUnits: [{ value: "kn", label: "Knots" }, { value: "mph", label: "mph" }, { value: "kmh", label: "km/h" }]
    readonly property var tempUnits: [{ value: "F", label: "Fahrenheit" }, { value: "C", label: "Celsius" }]
    readonly property var orientations: [{ value: "north", label: "North up" }, { value: "head", label: "Head up" }, { value: "course", label: "Course up" }]
    readonly property var paletteModes: [{ value: "auto", label: "Auto" }, { value: "day", label: "Day" }, { value: "dusk", label: "Dusk" }, { value: "night", label: "Night" }]
    readonly property var lockTimeouts: [{ value: 0, label: "Off" }, { value: 30, label: "30 s" }, { value: 60, label: "1 min" }, { value: 120, label: "2 min" }, { value: 300, label: "5 min" }]
    readonly property var trackIntervals: [{ value: 1, label: "1 s" }, { value: 5, label: "5 s" }, { value: 10, label: "10 s" }, { value: 30, label: "30 s" }]
    readonly property var trackDistances: [{ value: 5, label: "5 m" }, { value: 10, label: "10 m" }, { value: 25, label: "25 m" }]

    // Depth shown in the current depth unit.
    function depthText(m) {
        const v = m / metresPerUnit
        return depthUnit === "ft" ? Math.round(v) + " ft" : v.toFixed(1) + " " + depthUnit
    }
    function round4(x) { return Math.round(x * 10000) / 10000 }

    // which: "shallow", "safety" or "deep"; dir: +1 or -1.
    function stepDepth(which, dir) {
        let d = { shallow: settings.shallowM, safety: settings.safetyM, deep: settings.deepM }
        d[which] = round4(d[which] + dir * metresPerStep)
        if (settings.setDepths(d.shallow, d.safety, d.deep)) {
            depthError = ""
            return
        }
        const why = settings.depthsProblem(d.shallow, d.safety, d.deep)
        depthError = why !== "" ? why : "The depths could not be saved."
    }
    function stepDiagonal(dir) {
        const v = Math.round((settings.panelDiagonalIn + dir * 0.1) * 10) / 10
        if (v >= 7 && v <= 15) settings.panelDiagonalIn = v
    }

    // Opens the big list; apply(value) is called with the tapped choice.
    function openList(title, choices, current, apply) {
        list.title = title
        list.choices = choices
        list.current = current
        list.apply = apply
        list.visible = true
    }

    component Stepper: Item {
        id: st
        property string title: ""
        property string value: ""
        property string valueName: ""
        signal minus()
        signal plus()
        width: column.width
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
            BigButton { objectName: st.valueName + "Minus"; width: Units.mm(14); text: "-"; onClicked: st.minus() }
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
            BigButton { objectName: st.valueName + "Plus"; width: Units.mm(14); text: "+"; onClicked: st.plus() }
        }
    }
    component ChoiceRow: BigButton {
        width: column.width
        contentItem: Label {
            text: parent.text
            color: Theme.buttonText
            font: parent.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    Flickable {
        id: scroller
        objectName: "settingsScroller"
        anchors.fill: parent
        anchors.margins: Units.mm(3)
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true

        Column {
            id: column
            width: Math.max(Units.mm(100), Math.min(scroller.width, Units.mm(150)))
            spacing: Units.mm(2)

            ChoiceRow {
                objectName: "row-depthUnit"
                text: "Depth unit: " + page.choiceLabel(page.depthUnits, page.settings.depthUnit)
                onClicked: page.openList("Depth unit", page.depthUnits, page.settings.depthUnit, v => { page.settings.depthUnit = v; page.depthError = "" })
            }
            ChoiceRow {
                objectName: "row-speedUnit"
                text: "Speed unit: " + page.choiceLabel(page.speedUnits, page.settings.speedUnit)
                onClicked: page.openList("Speed unit", page.speedUnits, page.settings.speedUnit, v => page.settings.speedUnit = v)
            }
            ChoiceRow {
                objectName: "row-tempUnit"
                text: "Temperature unit: " + page.choiceLabel(page.tempUnits, page.settings.tempUnit)
                onClicked: page.openList("Temperature unit", page.tempUnits, page.settings.tempUnit, v => page.settings.tempUnit = v)
            }
            ChoiceRow {
                objectName: "row-applyOffset"
                text: "Apply transducer offset: " + (page.settings.applyDepthOffset ? "On" : "Off")
                onClicked: page.settings.applyDepthOffset = !page.settings.applyDepthOffset
            }

            Stepper {
                title: "Shallow depth"
                valueName: "shallow"
                value: page.depthText(page.settings.shallowM)
                onMinus: page.stepDepth("shallow", -1)
                onPlus: page.stepDepth("shallow", 1)
            }
            Stepper {
                title: "Safety depth"
                valueName: "safety"
                value: page.depthText(page.settings.safetyM)
                onMinus: page.stepDepth("safety", -1)
                onPlus: page.stepDepth("safety", 1)
            }
            Stepper {
                title: "Deep depth"
                valueName: "deep"
                value: page.depthText(page.settings.deepM)
                onMinus: page.stepDepth("deep", -1)
                onPlus: page.stepDepth("deep", 1)
            }
            Label {
                objectName: "depthError"
                visible: page.depthError !== ""
                width: column.width
                text: page.depthError
                color: Theme.text
                font.pixelSize: Units.mm(4)
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Label {
                width: column.width
                text: "Chart depths are in feet"
                color: Theme.text
                font.pixelSize: Units.mm(3.5)
            }

            ChoiceRow {
                objectName: "row-orientation"
                text: "Orientation: " + page.choiceLabel(page.orientations, page.settings.orientation)
                onClicked: page.openList("Orientation", page.orientations, page.settings.orientation, v => page.settings.orientation = v)
            }
            ChoiceRow {
                objectName: "row-paletteMode"
                text: "Palette: " + page.choiceLabel(page.paletteModes, page.settings.paletteMode)
                onClicked: page.openList("Palette", page.paletteModes, page.settings.paletteMode, v => page.settings.paletteMode = v)
            }
            ChoiceRow {
                objectName: "row-touchLock"
                text: "Touch lock timeout: " + page.choiceLabel(page.lockTimeouts, page.settings.touchLockTimeoutS)
                onClicked: page.openList("Touch lock timeout", page.lockTimeouts, page.settings.touchLockTimeoutS, v => page.settings.touchLockTimeoutS = v)
            }
            Stepper {
                title: "Panel diagonal"
                valueName: "diagonal"
                value: page.settings.panelDiagonalIn.toFixed(1) + " in"
                onMinus: page.stepDiagonal(-1)
                onPlus: page.stepDiagonal(1)
            }
            ChoiceRow {
                objectName: "row-trackInterval"
                text: "Track interval: " + page.choiceLabel(page.trackIntervals, page.settings.trackIntervalS)
                onClicked: page.openList("Track interval", page.trackIntervals, page.settings.trackIntervalS, v => page.settings.trackIntervalS = v)
            }
            ChoiceRow {
                objectName: "row-trackDistance"
                text: "Track minimum distance: " + page.choiceLabel(page.trackDistances, page.settings.trackMinDistanceM)
                onClicked: page.openList("Track minimum distance", page.trackDistances, page.settings.trackMinDistanceM, v => page.settings.trackMinDistanceM = v)
            }
            ChoiceRow {
                objectName: "editOverlaysButton"
                text: "Edit overlays"
                onClicked: page.editOverlays()
            }
            ChoiceRow {
                objectName: "aboutButton"
                text: "About"
                onClicked: page.showAbout()
            }
        }
    }

    // The big list: covers the page while open.
    Rectangle {
        id: list
        objectName: "settingsList"
        property string title: ""
        property var choices: []
        property var current: null
        property var apply: null
        anchors.fill: parent
        visible: false
        color: Theme.background

        MouseArea { anchors.fill: parent } // swallow touches

        Label {
            anchors { left: parent.left; verticalCenter: listDone.verticalCenter; leftMargin: Units.mm(3) }
            text: list.title
            color: Theme.text
            font.pixelSize: Units.mm(5)
            font.bold: true
        }
        BigButton {
            id: listDone
            objectName: "listDone"
            anchors { right: parent.right; top: parent.top; margins: Units.mm(2) }
            width: Math.max(implicitWidth, Units.mm(25))
            text: "Done"
            onClicked: list.visible = false
        }
        Flickable {
            anchors { top: listDone.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: Units.mm(2) }
            contentHeight: choiceColumn.implicitHeight
            clip: true
            Column {
                id: choiceColumn
                spacing: Units.mm(1.5)
                Repeater {
                    model: list.choices
                    BigButton {
                        required property var modelData
                        objectName: "choice-" + modelData.value
                        width: Units.mm(60)
                        text: modelData.label
                        highlighted: list.current === modelData.value
                        onClicked: { list.apply(modelData.value); list.visible = false }
                    }
                }
            }
        }
    }
}
