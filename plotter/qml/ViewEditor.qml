import QtQuick
import QtQuick.Controls.Basic

// The view editor over the shown view (spec 6.7): the view stays live underneath, and over it three
// floating buttons in the middle of the chart's corner area (or of the page for a cell view),
// stacked: Setup, Done, Cancel. A tap on a slot opens the slot sheet and selects the slot (its
// resize handle shows); a tap on a cell opens the cell sheet. Every slot change is clamped against
// the other slots at their drawn sizes (chartPage.maxMmFor) and the sheet shows what was applied.
// Setup opens the Setup sheet (name, icon, chart, layout, favourite, delete). The floating buttons
// hide while any sheet is open. The slot and cell sheets also open on their own, with editing off
// (the live view hold shortcut, spec 6.9).
// Shares its parent with the chart and cell pages, so their coordinates are its own.
Item {
    id: editor
    required property var draft     // ViewDraft
    required property var views     // ViewsModel
    property real rightInset: 0     // the tab bar strip over the page's right edge
    property bool editing: false
    property Item chartPage: null
    property Item cellPage: null
    property string selectedSlot: ""
    property int selectedCell: -1
    property string sheet: ""       // the open sheet: slot, cell, setup or none
    readonly property bool sheetOpen: sheet !== ""
    readonly property Item setupSheet: setupSheet
    signal setupRequested()
    signal doneRequested()
    signal cancelRequested()
    signal sheetClosed()            // a slot or cell sheet's Done
    signal deleteRequested()        // the Setup sheet's Delete, confirmed

    objectName: "viewEditor"
    onEditingChanged: {
        selectedSlot = ""
        selectedCell = -1
        closeSheets()
    }

    // Where the buttons go: the chart's corner area, or the page left of the strip.
    readonly property rect area: chartPage && chartPage.visible
        ? Qt.rect(chartPage.cornerAreaItem.x, chartPage.cornerAreaItem.y, chartPage.cornerAreaItem.width, chartPage.cornerAreaItem.height)
        : Qt.rect(0, 0, width - rightInset, height)

    function closeSheets() { sheet = "" }
    function openSetup() {
        selectedSlot = ""
        selectedCell = -1
        sheet = "setup"
    }
    onSetupRequested: openSetup()
    function slotJson(slotId) { return draft.toJson().slots.find(s => s.id === slotId) }
    // The half of the page away from the item.
    function atTopFor(it) { return it.mapToItem(editor, 0, it.height / 2).y > height / 2 }

    function openSlotSheet(slotId) {
        const s = slotJson(slotId)
        const it = chartPage ? chartPage.slotItem(slotId) : null
        if (!s || !it) return
        selectedSlot = slotId
        slotSheet.slotId = slotId
        slotSheet.atTop = atTopFor(it)
        showSlot(s)
        sheet = "slot"
    }
    function openCellSheet(index) {
        const fields = draft.toJson().cells.fields
        const it = cellPage ? cellPage.cellItem(index) : null
        if (index < 0 || index >= fields.length || !it) return
        selectedCell = index
        cellSheet.field = fields[index]
        cellSheet.atTop = atTopFor(it)
        sheet = "cell"
    }
    function showSlot(s) {
        slotSheet.on = s.on
        slotSheet.field = s.field
        slotSheet.sizeMm = s.sizeMm
        slotSheet.maxMm = chartPage.maxMmFor(s.id)
    }
    // The slot in the draft at the wanted size within [6, the room left].
    function applySlot(slotId, on, field, wantedMm) {
        draft.setSlot(slotId, on, field, Math.max(6, Math.min(wantedMm, chartPage.maxMmFor(slotId))))
        if (sheet === "slot" && slotSheet.slotId === slotId) showSlot(slotJson(slotId))
    }
    // A handle drag: the size whose modelled box reaches the dragged inner corner (or edge). The
    // distance is measured inwards from the outer edge and stops at 0, so a finger past the outer
    // edge holds the size at the floor.
    function dragSlot(slotId, innerX, innerY) {
        const it = chartPage.slotItem(slotId)
        const s = slotJson(slotId)
        const d = Math.max(0, it.horizontalBar ? (it.topSide ? innerY - it.outerY : it.outerY - innerY)
                                               : (it.leftSide ? innerX - it.outerX : it.outerX - innerX))
        const mm = it.horizontalBar ? (d / Units.pxPerMm - it.fixedHMm) / it.hPerMm
                                    : (d / Units.pxPerMm - it.fixedWMm) / it.wPerMm
        applySlot(slotId, s.on, s.field, mm)
    }

    Column {
        visible: editor.editing && !editor.sheetOpen
        x: editor.area.x + (editor.area.width - width) / 2
        y: editor.area.y + (editor.area.height - height) / 2
        spacing: Units.mm(1.5)
        readonly property real buttonWidth: Units.mm(32)

        BigButton {
            id: setup
            objectName: "editorSetup"
            width: parent.buttonWidth
            text: "Setup"
            onClicked: editor.setupRequested()
            contentItem: Item {
                implicitWidth: row.implicitWidth
                implicitHeight: row.implicitHeight
                Row {
                    id: row
                    anchors.centerIn: parent
                    spacing: Units.mm(1.5)
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Units.mm(6)
                        height: Units.mm(6)
                        name: "settings"
                    }
                    Label {
                        anchors.verticalCenter: parent.verticalCenter
                        text: setup.text
                        font: setup.font
                        color: Theme.buttonText
                    }
                }
            }
        }
        BigButton {
            objectName: "editorDone"
            width: parent.buttonWidth
            text: "Done"
            onClicked: editor.doneRequested()
        }
        BigButton {
            objectName: "editorCancel"
            width: parent.buttonWidth
            text: "Cancel"
            onClicked: editor.cancelRequested()
        }
    }

    SlotSheet {
        id: slotSheet
        visible: editor.sheet === "slot"
        rightInset: editor.rightInset
        fieldChoices: editor.draft.slots.fieldChoices
        onChanged: (on, field, sizeMm) => editor.applySlot(slotId, on, field, sizeMm)
        onClosed: { editor.closeSheets(); editor.sheetClosed() }
    }
    SetupSheet {
        id: setupSheet
        visible: editor.sheet === "setup"
        draft: editor.draft
        views: editor.views
        rightInset: editor.rightInset
        onClosed: editor.closeSheets()
        onDeleteRequested: editor.deleteRequested()
    }
    CellSheet {
        id: cellSheet
        visible: editor.sheet === "cell"
        rightInset: editor.rightInset
        fieldChoices: editor.draft.cells.fieldChoices
        onFieldChosen: (field) => {
            editor.draft.setCellField(editor.selectedCell, field)
            cellSheet.field = editor.draft.toJson().cells.fields[editor.selectedCell]
        }
        onClosed: { editor.closeSheets(); editor.sheetClosed() }
    }
}
