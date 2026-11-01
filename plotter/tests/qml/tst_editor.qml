import QtQuick
import QtTest
import CheekyMarine
import "Helpers.js" as H

// The view editor over the shown view: its floating Setup, Done and Cancel, the inert bar, the slot
// sheet (show, field, size with + and -), the cell sheet, the resize handle, Cancel and Done, and the
// live hold shortcut.
TestCase {
    id: testCase
    name: "Editor"
    width: 1280
    height: 800
    visible: true // TestCase is invisible by default, and so would be everything created in it
    when: windowShown

    QtObject {
        id: chartStub
        property bool follow: true
        property bool fishAvailable: true
        property string mode: "nav"
        property string notice: "NOAA ENC data. Not certified for navigation."
        property bool noPosition: false
        property var legend: [{ abbr: "Blds", meaning: "boulders", kind: "type" }]
        property var aisSelection: ({})
        function targetAt(p, r) { return undefined }
        function selectAt(p, r) {}
        function clearTarget() {}
        function zoomIn() {}
        function zoomOut() {}
        function zoomBy(d) {}
        function recenter() { follow = true }
    }
    QtObject {
        id: paletteStub
        property string palette: "day"
    }
    Component {
        id: mapStub
        Item {
            signal userGesture()
            property int moves: 0
            function moveBy(p) { moves++ }
            function scaleBy(f, p) {}
        }
    }
    Component { id: mainComp; Main {} }
    Component { id: spyComp; SignalSpy {} }

    function init() {
        failOnWarning(/.*/)
        fixture.reset()
        chartStub.follow = true
        chartStub.mode = "nav"
        Units.windowWidth = 1280
        Units.windowHeight = 800
        Units.diagonalIn = 10.1
    }

    function makeMain(w, h) {
        const main = createTemporaryObject(mainComp, testCase, {
            width: w, height: h,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), paletteController: paletteStub,
            settings: fixture.settings, vessel: fixture.vessel, appInfo: fixture.appInfo,
            views: fixture.views, draft: fixture.draft,
            touchLock: fixture.touchLock, tracksController: fixture.tracksController
        })
        verify(main, "Main")
        tryCompare(main, "width", w)
        H.byName(main.contentItem, "splash").visible = false
        waitForRendering(main.contentItem)
        return main
    }
    function find(root, name) {
        const it = H.byName(root, name)
        verify(it, name)
        return it
    }
    function m(main, name) { return find(main.contentItem, name) }
    function slotOf(json, id) {
        const s = json.slots.filter(x => x.id === id)
        verify(s.length === 1, "slot " + id)
        return s[0]
    }
    function draftSlot(id) { return slotOf(fixture.draft.toJson(), id) }
    function barShown(main) {
        const bar = m(main, "tabBar")
        return Math.abs(bar.x - (main.width - bar.width)) < 0.5
    }
    function barHidden(main) { return m(main, "tabBar").x >= main.width - 1 }
    function hold(it, done) {
        verify(it, "nothing to hold")
        mousePress(it)
        tryVerify(done, 3000, "the hold took effect")
        mouseRelease(it)
    }
    // Home, the tile menu of `id`, Edit.
    function editFromHome(main, id) {
        mouseClick(m(main, "tab-home"))
        compare(main.page, "home")
        const menu = m(main, "tileMenu")
        hold(m(main, "tile-" + id), () => menu.visible)
        waitForRendering(menu)
        mouseClick(find(menu, "menu-edit"))
        verify(main.editing, "Edit opens the editor")
        compare(main.page, "view")
        compare(fixture.views.currentId, id)
        waitForRendering(main.contentItem)
    }
    function inside(a, b) {
        return a.x >= b.x - 0.5 && a.y >= b.y - 0.5 && a.x + a.w <= b.x + b.w + 0.5 && a.y + a.h <= b.y + b.h + 0.5
    }

    function test_editorButtonsAndInertBar_data() { return H.sizes() }
    function test_editorButtonsAndInertBar(data) {
        const main = makeMain(data.w, data.h)
        main.hideDelayMs = 100
        main.editView("shipped-nav")
        verify(main.editing)
        const page = m(main, "chartPage")
        verify(page.editing)
        waitForRendering(page)
        const area = H.box(m(main, "cornerArea"), main.contentItem)
        const slots = H.findAll(page, it => it.objectName.startsWith("slot-") && it.visible)
        compare(slots.length, 8, "all eight outlined")
        for (const name of ["editorSetup", "editorDone", "editorCancel"]) {
            const b = m(main, name)
            verify(b.visible, name)
            verify(b.width >= Units.mm(12) - 0.5 && b.height >= Units.mm(12) - 0.5, name + " is " + b.width + "x" + b.height)
            verify(inside(H.box(b, main.contentItem), area), name + " inside the corner area")
            for (const s of slots) verify(!H.overlaps(b, s, main.contentItem), name + " clear of " + s.objectName)
        }
        const setup = m(main, "editorSetup")
        compare(H.findAll(setup, it => it.name === "settings" && it.sourceSize !== undefined).length, 1, "the gear")
        verify(H.findAll(setup, it => it.text === "Setup" && it.isBigButton !== true).length === 1, "the text")
        const done = m(main, "editorDone"), cancel = m(main, "editorCancel")
        verify(H.box(setup, main.contentItem).y < H.box(done, main.contentItem).y, "Setup over Done")
        verify(H.box(done, main.contentItem).y < H.box(cancel, main.contentItem).y, "Done over Cancel")

        const bar = m(main, "tabBar")
        compare(bar.enabled, false)
        fuzzyCompare(bar.opacity, 0.45, 0.01)
        mouseClick(m(main, "tab-home"))
        compare(main.page, "view", "the bar is inert")
        wait(300)
        verify(bar.shown, "the bar does not hide while editing")
        verify(barShown(main))
    }

    // The editor's layout is the live one: on slots draw at their live sizes, and every off slot is
    // a 12 mm outline (a square for a corner, a strip along its edge for a bar) inside the page that
    // takes no room. An off corner overlaps no on slot; an off bar is a faint hint an on corner may
    // lie over, under it.
    function test_offSlotsTakeNoRoomInTheEditor_data() { return H.sizes() }
    function test_offSlotsTakeNoRoomInTheEditor(data) {
        const main = makeMain(data.w, data.h)
        const page = m(main, "chartPage")
        waitForRendering(page)
        const live = [page.drawn.TL, page.drawn.TR]
        const liveMap = H.box(m(main, "mapArea"), page)
        main.editView("shipped-nav")
        waitForRendering(page)
        compare([page.drawn.TL, page.drawn.TR], live, "TL and TR drawn as on the live view")
        compare(H.box(m(main, "mapArea"), page), liveMap, "the map area as on the live view")
        const room = { x: 0, y: 0, w: page.width - page.rightInset, h: page.height }
        const on = ["TL", "TR"].map(id => m(main, "slot-" + id))
        for (const id of ["BL", "BR", "Top", "Bottom", "Left", "Right"]) {
            const s = m(main, "slot-" + id)
            verify(s.visible && !s.on && !s.takesRoom, id + " outlined, off, no room")
            const b = H.box(s, page)
            verify(inside(b, room), id + " inside the page")
            const bar = id === "Top" || id === "Bottom" || id === "Left" || id === "Right"
            if (id !== "Left" && id !== "Right") fuzzyCompare(b.h, Units.mm(12), 0.5)
            if (id !== "Top" && id !== "Bottom") fuzzyCompare(b.w, Units.mm(12), 0.5)
            for (const o of on) {
                if (bar) verify(s.z < o.z, id + " under " + o.objectName)
                else verify(!H.overlaps(s, o, page), id + " clear of " + o.objectName)
            }
        }
        fuzzyCompare(H.box(m(main, "slot-Top"), page).w, room.w, 0.5)
        fuzzyCompare(H.box(m(main, "slot-Left"), page).h, page.height - m(main, "noticeBar").height, 0.5)
        fixture.draft.setSlot("BL", false, "cog", 40)
        fixture.draft.setSlot("Top", false, "time", 30)
        compare([page.drawn.TL, page.drawn.TR], live, "off slots change nothing")
        fuzzyCompare(m(main, "slot-BL").height, Units.mm(12), 0.5)
        fuzzyCompare(m(main, "slot-Top").height, Units.mm(12), 0.5)
        // A tap on an off bar's strip opens its sheet.
        mouseClick(m(main, "slot-Bottom"))
        compare(find(m(main, "viewEditor"), "slotSheet").slotId, "Bottom")
    }

    // Turning a slot On from its sheet makes it take room at once, clamped against the others.
    function test_cornerOnTakesRoomAtOnce() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        fixture.draft.setSlot("BL", false, "cog", 100)
        const page = m(main, "chartPage")
        mouseClick(m(main, "slot-BL"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        verify(sheet.visible)
        mouseClick(find(sheet, "choice-on"))
        const bl = m(main, "slot-BL")
        verify(bl.on && bl.takesRoom)
        const applied = draftSlot("BL").sizeMm
        verify(applied < 100, "clamped: " + applied)
        verify(applied <= page.maxMmFor("BL") + 0.05, applied + " within " + page.maxMmFor("BL"))
        compare(sheet.sizeMm, applied, "the sheet shows the applied size")
        fuzzyCompare(sheet.maxMm, page.maxMmFor("BL"), 0.05)
        waitForRendering(page)
        verify(bl.height > Units.mm(12) + 0.5, "BL is a full box now")
        verify(!H.overlaps(bl, m(main, "slot-TL"), page), "BL clear of TL")
        mouseClick(find(sheet, "sheetDone"))

        // A bar: Top On moves the map area and the top corners down.
        const map = m(main, "mapArea"), tl = m(main, "slot-TL")
        const mapY = H.box(map, page).y, tlY = H.box(tl, page).y
        mouseClick(m(main, "slot-Top")) // mid-length, clear of the corners
        compare(sheet.slotId, "Top")
        mouseClick(find(sheet, "choice-on"))
        const top = m(main, "slot-Top")
        verify(top.on && top.takesRoom)
        compare(sheet.sizeMm, draftSlot("Top").sizeMm)
        waitForRendering(page)
        verify(H.box(map, page).y > mapY + 0.5, "the map area moved down")
        verify(H.box(tl, page).y > tlY + 0.5, "TL moved down")
        verify(!H.overlaps(top, tl, page), "Top clear of TL")
    }

    // The dimmed bar swallows presses: a drag on it pans nothing.
    function test_inertBarSwallowsPresses() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        const bar = m(main, "tabBar")
        const touched = createTemporaryObject(spyComp, testCase, { target: bar, signalName: "touched" })
        // The map runs under the strip (no Right bar is on): the press is taken over the bar.
        const cover = m(main, "inertBarCover")
        mousePress(bar, bar.width / 2, bar.height / 2)
        verify(cover.pressed, "the press is taken over the bar")
        mouseRelease(bar, bar.width / 2, bar.height / 2)
        mouseDrag(bar, bar.width / 2, bar.height - Units.mm(0.5), -Units.mm(30), 0)
        mouseDrag(bar, bar.width / 2, bar.height / 2, -Units.mm(30), 0)
        compare(main.chartMap.moves, 0, "no pan")
        compare(touched.count, 0)
        verify(bar.shown)
        verify(main.editing)
        compare(main.page, "view")
    }

    function test_slotSheetEditsTheDraftAndDoneSaves() {
        const main = makeMain(1024, 600)
        editFromHome(main, "shipped-nav")
        compare(main.editorFrom, "home")
        const editor = m(main, "viewEditor")
        const sheet = find(editor, "slotSheet")
        verify(!sheet.visible)
        // TL and TR at 25 mm leave no room in their row to grow: TL off first.
        mouseClick(m(main, "slot-TL"))
        mouseClick(find(sheet, "choice-off"))
        mouseClick(find(sheet, "sheetDone"))
        verify(!draftSlot("TL").on)
        mouseClick(m(main, "slot-TR"))
        verify(sheet.visible, "the slot sheet")
        compare(editor.selectedSlot, "TR")
        compare(sheet.slotId, "TR")
        verify(!sheet.atTop, "TR is in the top half: the sheet takes the bottom half")
        const s = H.box(sheet, editor)
        fuzzyCompare(s.h, editor.height / 2, 1)
        fuzzyCompare(s.y, editor.height / 2, 1)
        waitForRendering(sheet)
        H.checkBigButtons(testCase, Units, sheet)
        for (const b of H.findAll(sheet, it => it.isBigButton === true && it.visible))
            verify(inside(H.box(b, editor), s), b.objectName + " inside the sheet")
        verify(find(m(main, "chartPage"), "handle-TR").visible, "the selected slot's handle")

        const value = find(sheet, "sizeValue")
        compare(value.text, "25.0 mm")
        const plus = find(sheet, "sizePlus")
        mouseClick(plus)
        compare(value.text, "25.5 mm")
        compare(draftSlot("TR").sizeMm, 25.5)
        mousePress(plus)
        // The hold under test: 400 ms, then 2 mm per second; every value it shows on the way is on
        // the 0.5 mm grid.
        const seen = []
        for (const t0 = Date.now(); Date.now() - t0 < 1400;) {
            wait(40)
            seen.push(sheet.sizeMm)
        }
        mouseRelease(plus)
        for (const v of seen) compare(v * 2, Math.round(v * 2), "on the 0.5 mm grid while held: " + v)
        const grown = draftSlot("TR").sizeMm
        verify(Math.abs(grown - 27.5) <= 0.5, "about 2 mm more: " + grown)
        compare(grown * 2, Math.round(grown * 2), "on the 0.5 mm grid: " + grown)
        compare(value.text, grown.toFixed(1) + " mm")
        compare(sheet.sizeMm, grown)

        mouseClick(find(sheet, "choice-field-stw"))
        compare(draftSlot("TR").field, "stw")
        mouseClick(find(sheet, "choice-off"))
        verify(!draftSlot("TR").on)
        mouseClick(find(sheet, "sheetDone"))
        verify(!sheet.visible)
        mouseClick(m(main, "editorDone"))
        const stored = slotOf(fixture.views.viewJson("shipped-nav"), "TR")
        compare(stored.on, false)
        compare(stored.field, "stw")
        compare(stored.sizeMm, grown)
        compare(main.editing, false)
        compare(main.page, "view")
        verify(!sheet.visible)
        verify(m(main, "tabBar").enabled, "the bar back")
    }

    // Sliding off a held + stops the repeat.
    function test_slideOffStopsTheRepeat() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        mouseClick(m(main, "slot-BL"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        const plus = find(sheet, "sizePlus")
        const start = sheet.sizeMm
        mousePress(plus)
        tryVerify(() => sheet.sizeMm > start, 2000, "the repeat runs")
        mouseMove(plus, -Units.mm(20), plus.height / 2, -1, Qt.LeftButton) // off the button, still pressed
        const at = sheet.sizeMm
        wait(600) // the repeat would move it 1.2 mm in this time
        compare(sheet.sizeMm, at, "stopped")
        mouseRelease(plus, -Units.mm(20), plus.height / 2)
        compare(sheet.sizeMm, at)
    }

    function test_minusStepsAndFloorsAtSix() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        mouseClick(m(main, "slot-BL"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        compare(sheet.sizeMm, 14)
        const minus = find(sheet, "sizeMinus")
        mouseClick(minus)
        compare(draftSlot("BL").sizeMm, 13.5)
        for (let i = 0; i < 20; ++i) mouseClick(minus)
        compare(draftSlot("BL").sizeMm, 6)
        compare(find(sheet, "sizeValue").text, "6.0 mm")
        verify(sheet.atTop, "BL is in the bottom half: the sheet takes the top half")
    }

    function test_cancelDiscardsEverything() {
        const main = makeMain(1024, 600)
        editFromHome(main, "shipped-nav")
        const before = fixture.views.viewJson("shipped-nav")
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        mouseClick(m(main, "slot-TR"))
        mouseClick(find(sheet, "sizeMinus"))
        mouseClick(find(sheet, "choice-off"))
        mouseClick(find(sheet, "sheetDone")) // the sheet covers the bottom half
        fixture.draft.chart = "fish" // as a Setup change would
        chartStub.mode = "fish"
        verify(fixture.draft.dirty)
        mouseClick(m(main, "editorCancel"))
        compare(fixture.draft.toJson(), fixture.views.viewJson("shipped-nav"))
        compare(fixture.views.viewJson("shipped-nav"), before)
        compare(chartStub.mode, "nav", "the chart mode back")
        compare(main.page, "home", "back where the editor was entered")
        compare(main.editing, false)
        verify(!sheet.visible)
    }

    function test_cancelOnNewViewRemovesIt() {
        const main = makeMain(1024, 600)
        fixture.views.currentId = "shipped-fish"
        mouseClick(m(main, "tab-home"))
        mouseClick(m(main, "tile-new"))
        compare(fixture.views.count, 4)
        verify(main.editing)
        verify(main.editingNew)
        verify(main.setupRequestedOnOpen, "a new view asks for Setup")
        const id = fixture.views.currentId
        compare(fixture.views.viewJson(id).name, "View 4")
        mouseClick(m(main, "editorCancel"))
        compare(fixture.views.count, 3)
        compare(fixture.views.indexOf(id), -1)
        compare(fixture.views.currentId, "shipped-fish", "the view current before New")
        compare(fixture.draft.id, "shipped-fish")
        compare(main.page, "home")
        compare(main.editing, false)
        verify(!main.editingNew)
    }

    function test_sizeClampsToTheRoomLeft() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        const page = m(main, "chartPage")
        mouseClick(m(main, "slot-TR"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        const plus = find(sheet, "sizePlus")
        let last = -1
        for (let i = 0; i < 200 && sheet.sizeMm !== last; ++i) {
            last = sheet.sizeMm
            mouseClick(plus)
        }
        compare(sheet.sizeMm, last, "the size stopped")
        const max = page.maxMmFor("TR")
        verify(max >= 6, "max " + max)
        const applied = draftSlot("TR").sizeMm
        verify(Math.abs(applied - max) <= 0.11, "stopped at the max: " + applied + " vs " + max)
        compare(sheet.sizeMm, applied, "the shown value is the applied one")
        compare(find(sheet, "sizeValue").text, applied.toFixed(1) + " mm")
        waitForRendering(page)
        const tl = m(main, "slot-TL"), tr = m(main, "slot-TR")
        verify(!H.overlaps(tl, tr, page), "TL and TR apart")
        const room = { x: 0, y: 0, w: page.width - page.rightInset, h: page.height }
        for (const s of [tl, tr]) verify(inside(H.box(s, page), room), s.objectName + " inside the page")
    }

    // A mouse drag from the centre of `it` by dx, in steps, in window coordinates (the handle moves
    // under the mouse as the slot resizes); midway(), when given, runs at half way, still pressed.
    function dragBy(main, it, dx, midway) {
        const w = main.contentItem
        const p = it.mapToItem(w, it.width / 2, it.height / 2)
        mousePress(w, p.x, p.y)
        for (let i = 1; i <= 10; ++i) {
            mouseMove(w, p.x + dx * i / 10, p.y, -1, Qt.LeftButton)
            if (i === 5 && midway) midway()
        }
        mouseRelease(w, p.x + dx, p.y)
    }

    function test_dragHandleResizesLive() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        const page = m(main, "chartPage")
        mouseClick(m(main, "slot-TL"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        verify(!sheet.atTop)
        const handle = find(page, "handle-TL")
        verify(handle.visible)
        verify(Math.abs(handle.width - Units.mm(12)) < 0.5 && Math.abs(handle.height - Units.mm(12)) < 0.5)
        const tl = m(main, "slot-TL")
        const hb = H.box(handle, tl)
        verify(hb.x + hb.w > tl.width - 1 && hb.y + hb.h > tl.height - 1, "on TL's inner (bottom right) corner")
        waitForRendering(page)
        const start = draftSlot("TL").sizeMm
        const moves = createTemporaryObject(spyComp, testCase, { target: page, signalName: "handleDragged" })
        dragBy(main, handle, -Units.mm(20), () => verify(draftSlot("TL").sizeMm < start, "live, before the release"))
        verify(moves.count > 0, "the drag is reported")
        const shrunk = draftSlot("TL").sizeMm
        verify(shrunk < start && shrunk >= 6, "shrinks: " + start + " to " + shrunk)
        compare(sheet.sizeMm, shrunk, "the sheet shows it")
        waitForRendering(page)
        // As far left as the window goes, again until it stops: it stops at 6.
        for (let i = 0; i < 6 && draftSlot("TL").sizeMm > 6; ++i) {
            const h = find(page, "handle-TL")
            dragBy(main, h, 2 - h.mapToItem(main.contentItem, h.width / 2, 0).x)
            waitForRendering(page)
        }
        compare(draftSlot("TL").sizeMm, 6, "never below 6")
        waitForRendering(page)
        dragBy(main, find(page, "handle-TL"), Units.mm(100)) // 60 mm from 6 mm does not reach the room left now
        const max = page.maxMmFor("TL")
        const grown = draftSlot("TL").sizeMm
        verify(grown > 6, "grows: " + grown)
        verify(Math.abs(grown - max) <= 0.11, "stops at the clamp: " + grown + " vs " + max)

        // TR's handle dragged out past the page's right edge: the size stays at the floor.
        mouseClick(m(main, "slot-TR"))
        // Until it reaches the floor, then once more, each drag out past the outer edge.
        for (let i = 0, extra = 1; i < 6 && (draftSlot("TR").sizeMm > 6 || extra-- > 0); ++i) {
            const t = find(page, "handle-TR")
            dragBy(main, t, main.width + Units.mm(40) - t.mapToItem(main.contentItem, t.width / 2, 0).x)
            waitForRendering(page)
        }
        compare(draftSlot("TR").sizeMm, 6, "past the outer edge: still 6")
        mouseClick(m(main, "slot-TL"))

        // A finger, as on the panel.
        waitForRendering(page)
        const w = main.contentItem
        const f = find(page, "handle-TL")
        const p = f.mapToItem(w, f.width / 2, f.height / 2)
        touchEvent(w).press(0, w, p.x, p.y).commit()
        for (let i = 1; i <= 10; ++i) touchEvent(w).move(0, w, p.x - Units.mm(1) * i, p.y).commit()
        touchEvent(w).release(0, w, p.x - Units.mm(10), p.y).commit()
        verify(draftSlot("TL").sizeMm < grown, "a finger drag shrinks it too: " + draftSlot("TL").sizeMm)
    }

    function test_cellSheetChangesAField() {
        const main = makeMain(1024, 600)
        main.editView("shipped-big")
        const cells = m(main, "cellPage")
        verify(cells.visible)
        verify(cells.editing)
        mouseClick(m(main, "cell-1"))
        const editor = m(main, "viewEditor")
        compare(editor.selectedCell, 1)
        const sheet = find(editor, "cellSheet")
        verify(sheet.visible)
        verify(!find(editor, "slotSheet").visible)
        fuzzyCompare(H.box(sheet, editor).h, editor.height / 2, 1)
        waitForRendering(sheet)
        H.checkBigButtons(testCase, Units, sheet)
        mouseClick(find(sheet, "choice-field-wtemp"))
        mouseClick(find(sheet, "sheetDone"))
        verify(!sheet.visible)
        mouseClick(m(main, "editorDone"))
        compare(fixture.views.viewJson("shipped-big").cells.fields, ["depth", "wtemp"])
        compare(main.page, "view")
        compare(main.editing, false)

        // The sheet takes the half away from the cell.
        main.editView("shipped-big")
        fixture.draft.layout = "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"
        waitForRendering(cells)
        mouseClick(m(main, "cell-0"))
        verify(sheet.visible)
        verify(!sheet.atTop, "a top-half cell: the bottom half")
        fuzzyCompare(H.box(sheet, editor).y, editor.height / 2, 1)
        mouseClick(find(sheet, "sheetDone"))
        mouseClick(m(main, "cell-3"))
        verify(sheet.visible)
        verify(sheet.atTop, "a bottom-half cell: the top half")
        fuzzyCompare(H.box(sheet, editor).y, 0, 1)
        mouseClick(find(sheet, "sheetDone"))
        mouseClick(m(main, "editorCancel"))
    }

    function test_liveHoldOpensSheetAndSaves() {
        const main = makeMain(1024, 600)
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        hold(m(main, "slot-TL"), () => sheet.visible)
        verify(sheet.visible)
        compare(sheet.slotId, "TL")
        compare(main.editing, false)
        verify(!m(main, "editorDone").visible, "just the sheet")
        mouseClick(find(sheet, "choice-field-cog"))
        mouseClick(find(sheet, "sheetDone"))
        verify(!sheet.visible)
        compare(slotOf(fixture.views.viewJson("shipped-nav"), "TL").field, "cog")
        compare(main.editing, false)

        // A 15 mm drag from TL, then held still past the hold time: it pans and opens no sheet.
        const tl = m(main, "slot-TL"), w = main.contentItem
        const p = tl.mapToItem(w, tl.width / 2, tl.height / 2)
        mousePress(w, p.x, p.y)
        for (let i = 1; i <= 5; ++i) mouseMove(w, p.x + Units.mm(3) * i, p.y, -1, Qt.LeftButton)
        wait(900) // still pressed, longer than the 0.6 s hold: the hold under test
        verify(!sheet.visible, "a drag opens no sheet")
        verify(main.chartMap.moves > 0, "a drag from a slot pans the map")
        mouseRelease(w, p.x + Units.mm(15), p.y)
        verify(!sheet.visible)
    }

    // The hold is an established control: it leaves a hidden bar hidden, on a slot and on a cell.
    function test_liveHoldLeavesTheBarHidden() {
        const main = makeMain(1024, 600)
        const bar = m(main, "tabBar")
        const editor = m(main, "viewEditor")
        const slotSheet = find(editor, "slotSheet"), cellSheet = find(editor, "cellSheet")
        main.hideDelayMs = 200
        tryVerify(() => barHidden(main), 1000, "the bar slid off")
        hold(m(main, "slot-TL"), () => slotSheet.visible)
        verify(!bar.shown, "a slot hold leaves the bar hidden")
        mouseClick(find(slotSheet, "sheetDone"))
        verify(!bar.shown, "the sheet's Done too")

        fixture.views.currentId = "shipped-big"
        verify(m(main, "cellPage").visible)
        tryVerify(() => barHidden(main), 1000)
        hold(m(main, "cell-0"), () => cellSheet.visible)
        verify(!bar.shown, "a cell hold leaves the bar hidden")
        mouseClick(find(cellSheet, "choice-field-stw"))
        mouseClick(find(cellSheet, "sheetDone"))
        verify(!bar.shown)
        compare(fixture.views.viewJson("shipped-big").cells.fields, ["stw", "sog"])
    }
}
