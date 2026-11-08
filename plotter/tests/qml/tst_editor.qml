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
        property string palette: "day"
        property string spriteBase: ""
        property var legendCategories: [{ id: "seabed", title: "Seabed", needsPack: false,
                                          rows: [{ label: "boulders", note: "", kind: "seabed", text: "Blds" }] }]
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
    Component {
        id: pageComp
        Item { property alias keyboard: kb; Keyboard { id: kb; rightInset: Units.mm(17) } }
    }

    function init() {
        failOnWarning(/.*/)
        fixture.reset()
        chartStub.follow = true
        chartStub.mode = "nav"
        Units.windowWidth = 1280
        Units.windowHeight = 800
        Units.diagonalIn = 10.1
    }

    function makeMain(w, h, extra) {
        const main = createTemporaryObject(mainComp, testCase, Object.assign({
            width: w, height: h,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), paletteController: paletteStub,
            settings: fixture.settings, vessel: fixture.vessel, appInfo: fixture.appInfo,
            views: fixture.views, draft: fixture.draft,
            touchLock: fixture.touchLock, tracksController: fixture.tracksController
        }, extra || {}))
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
        fixture.settings.panelDiagonalIn = data.diagIn
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
        fixture.settings.panelDiagonalIn = data.diagIn
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
        // The hold under test: 400 ms, then 2 mm per second of real time from where it was; every
        // value it shows on the way is on the 0.5 mm grid and never falls. The rate is checked
        // against the measured time (the event loop can stall, and the repeat follows the clock).
        const pressedAt = Date.now()
        mousePress(plus)
        const seen = []
        while (Date.now() - pressedAt < 1400) {
            wait(40)
            seen.push(sheet.sizeMm)
        }
        const releasedAt = Date.now()
        verify(plus.repeating, "the repeat started")
        mouseRelease(plus)
        for (const v of seen) compare(v * 2, Math.round(v * 2), "on the 0.5 mm grid while held: " + v)
        for (let i = 1; i < seen.length; ++i) verify(seen[i] >= seen[i - 1], "never falls: " + seen)
        compare(plus.base, 25.5, "the repeat starts from the size shown")
        verify(plus.since - pressedAt >= 400 - 5, "the repeat waits 400 ms: " + (plus.since - pressedAt))
        const heldS = (releasedAt - plus.since) / 1000
        const grown = draftSlot("TR").sizeMm
        const want = plus.base + 2 * heldS
        verify(Math.abs(grown - want) <= 1.5,
               "2 mm per second: " + grown + " after " + heldS.toFixed(3) + " s, want about " + want.toFixed(2))
        verify(grown > plus.base, "it grew")
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

    // A thumb that drifts while holding + keeps the repeat: the sheet does not scroll when it fits,
    // so it takes no drag from the button (#68 review).
    function test_holdWithDriftKeepsTheRepeat() {
        const main = makeMain(1024, 600)
        main.editView("shipped-nav")
        mouseClick(m(main, "slot-BL"))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        const scroller = find(sheet, "slotSheetScroller")
        const plus = find(sheet, "sizePlus")
        const start = sheet.sizeMm
        mousePress(plus)
        tryVerify(() => sheet.sizeMm > start, 2000, "the repeat runs")
        for (let i = 1; i <= 5; ++i) mouseMove(plus, plus.width / 2, plus.height / 2 + 3 * i, -1, Qt.LeftButton)
        const at = sheet.sizeMm
        wait(600) // the repeat moves it 1.2 mm in this time
        verify(sheet.sizeMm > at, "still repeating after a 15 px drift: " + at + " to " + sheet.sizeMm)
        compare(scroller.contentY, 0, "nothing scrolled")
        mouseRelease(plus, plus.width / 2, plus.height / 2 + 15)
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
        mouseClick(m(main, "setupDone")) // a new view opens on its Setup sheet
        mouseClick(m(main, "editorCancel"))
        compare(fixture.views.count, 3)
        compare(fixture.views.indexOf(id), -1)
        compare(fixture.views.currentId, "shipped-fish", "the view current before New")
        compare(fixture.draft.id, "shipped-fish")
        compare(main.page, "home")
        compare(main.editing, false)
        verify(!main.editingNew)
    }

    // No two controls of the slot sheet overlap, none runs under Done or out of the sheet's width,
    // and each is inside the scrolled content, at every panel size, at its own diagonal and at the
    // 10.1 in default, at the 7 and 15 in ends of the setting, in either half (#68).
    function test_slotSheetControlsApart_data() {
        let out = []
        const cases = []
        for (const s of H.sizes()) {
            cases.push(s)
            if (s.diagIn !== 10.1) cases.push(Object.assign({}, s, { tag: s.tag + " at 10.1 in", diagIn: 10.1 }))
        }
        for (const d of [7, 15]) cases.push({ tag: "1024x600 at " + d + " in", w: 1024, h: 600, diagIn: d })
        for (const c of cases)
            for (const id of ["TL", "BL"]) out.push(Object.assign({}, c, { tag: c.tag + " " + id, id: id }))
        return out
    }
    function test_slotSheetControlsApart(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        main.editView("shipped-nav")
        mouseClick(m(main, "slot-" + data.id))
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        verify(sheet.visible)
        waitForRendering(sheet)
        const items = H.findAll(sheet, it => it.isBigButton === true && it.visible)
        items.push(find(sheet, "sizeValue"))
        verify(items.length >= 14, "controls found: " + items.length)
        for (let i = 0; i < items.length; ++i) {
            const a = items[i], name = a.objectName || a.text
            const b = H.box(a, sheet)
            verify(b.x >= -0.5 && b.x + b.w <= sheet.width + 0.5, name + " inside the sheet's width: " + JSON.stringify(b))
            for (let j = i + 1; j < items.length; ++j)
                verify(!H.overlaps(a, items[j], sheet), name + " and " + (items[j].objectName || items[j].text)
                       + " overlap: " + JSON.stringify(b) + " " + JSON.stringify(H.box(items[j], sheet)))
        }
        const scroller = find(sheet, "slotSheetScroller")
        const content = { x: 0, y: 0, w: scroller.contentWidth, h: scroller.contentHeight }
        for (const a of items)
            if (a.objectName !== "sheetDone")
                verify(inside(H.box(a, scroller.contentItem), content), (a.objectName || a.text) + " inside the scrolled content")
        // Above the 7 in end every size fits unscrolled: no row is cut at the sheet's bottom.
        if (data.diagIn > 7)
            verify(scroller.contentHeight <= scroller.height + 0.5, "fits unscrolled: " + scroller.contentHeight
                   + " in " + scroller.height)
        // The lowest control can be scrolled into view.
        let lowest = null
        for (const a of items)
            if (a.objectName !== "sheetDone" && (!lowest || H.box(a, scroller.contentItem).y > H.box(lowest, scroller.contentItem).y))
                lowest = a
        scroller.contentY = Math.max(0, scroller.contentHeight - scroller.height)
        waitForRendering(sheet)
        const low = H.box(lowest, scroller)
        verify(low.y >= -0.5 && low.y + low.h <= scroller.height + 0.5, lowest.objectName + " scrolls into view: " + JSON.stringify(low))
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
        fuzzyCompare(hb.x + hb.w / 2, tl.width, 1, "centered on TL's inner corner, x")
        fuzzyCompare(hb.y + hb.h / 2, tl.height, 1, "centered on TL's inner corner, y")
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

    // The handle is centered on the inner corner (corners) or the midpoint of the inner edge (bars),
    // half over the slot and half over the chart, and carries an arrow along the resize axis.
    function test_handleSitsOnTheInnerCornerOrEdgeWithAnArrow() {
        const main = makeMain(1280, 800)
        main.editView("shipped-nav")
        const page = m(main, "chartPage")
        const center = { TL: s => [s.width, s.height], TR: s => [0, s.height], BL: s => [s.width, 0], BR: s => [0, 0],
                         Top: s => [s.width / 2, s.height], Bottom: s => [s.width / 2, 0],
                         Left: s => [s.width, s.height / 2], Right: s => [0, s.height / 2] }
        const angle = { TL: 45, BR: 45, TR: 135, BL: 135, Top: 90, Bottom: 90, Left: 0, Right: 0 }
        for (const id of ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"]) {
            fixture.draft.setSlot(id, true, "sog", 8)
            waitForRendering(page)
            const slot = m(main, "slot-" + id)
            mouseClick(slot)
            const handle = find(page, "handle-" + id)
            verify(handle.visible, id + " handle")
            const hb = H.box(handle, slot)
            const [cx, cy] = center[id](slot)
            fuzzyCompare(hb.x + hb.w / 2, cx, 1, id + " center x")
            fuzzyCompare(hb.y + hb.h / 2, cy, 1, id + " center y")
            verify(Math.abs(hb.w - Units.mm(12)) < 0.5, id + " 12 mm")
            const arrow = find(handle, "handleArrow-" + id)
            verify(arrow.visible, id + " arrow")
            compare(arrow.rotation, angle[id], id + " arrow along the resize axis")
            verify(Qt.colorEqual(arrow.stroke, Theme.editHandleArrow), id + " arrow color")
            for (const p of [Theme.day, Theme.dusk, Theme.night])
                verify(Qt.color(p.editHandleArrow).hslLightness > Qt.color(p.editHandleDisc).hslLightness, "the arrow is lighter than the disc")
            // Done closes the sheet (it would cover the slots in the other half); the selection stays.
            const sheet = find(m(main, "viewEditor"), "slotSheet")
            mouseClick(find(sheet, "sheetDone"))
            verify(!sheet.visible, id + " sheet closed")
        }
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

    // The dev options --editor and --sheet: Main opens the editor on the shown view, then the sheet
    // its initial properties name.
    function test_mainInitialEditorAndSheet_data() {
        return [
            { tag: "editor", view: "shipped-nav", sheet: "", shown: "editorSetup" },
            { tag: "setup", view: "shipped-nav", sheet: "setup", shown: "setupSheet" },
            { tag: "gallery", view: "shipped-big", sheet: "gallery", shown: "layoutGallery" },
            { tag: "keyboard", view: "shipped-nav", sheet: "keyboard", shown: "keyboard" },
            { tag: "slot", view: "shipped-nav", sheet: "slot", shown: "slotSheet" },
            { tag: "cell", view: "shipped-big", sheet: "cell", shown: "cellSheet" },
        ]
    }
    function test_mainInitialEditorAndSheet(data) {
        fixture.views.currentId = data.view
        const main = makeMain(1024, 600, { editorOpen: true, sheet: data.sheet })
        const editor = m(main, "viewEditor")
        tryVerify(() => main.editing, 3000, "the editor opens")
        compare(main.page, "view")
        compare(fixture.views.currentId, data.view)
        const shown = find(editor, data.shown)
        tryVerify(() => shown.visible, 3000, data.shown + " shows")
        if (["setup", "gallery", "keyboard"].includes(data.sheet)) {
            compare(editor.sheet, "setup")
            verify(find(editor, "setupSheet").visible)
        }
        if (data.sheet === "keyboard") compare(shown.title, "Name")
        if (data.sheet === "slot") compare(shown.slotId, "TL")
        if (data.sheet === "cell") compare(editor.selectedCell, 0)
        if (data.sheet === "") compare(editor.sheet, "")
    }

    // The initial editor waits for the first frame, not for a fixed time: it is still closed at the
    // first swap after editorOpen and opens after it.
    function test_initialEditorOpensAfterFirstFrame() {
        const main = makeMain(1024, 600)
        verify(!main.editing)
        let swaps = 0, editingAtFirstSwap = null, swapsAtOpen = -1
        const onSwap = () => { if (++swaps === 1) editingAtFirstSwap = main.editing }
        const onEditing = () => { if (main.editing && swapsAtOpen < 0) swapsAtOpen = swaps }
        main.frameSwapped.connect(onSwap)
        main.editingChanged.connect(onEditing)
        main.editorOpen = true
        main.requestUpdate()
        tryVerify(() => swaps >= 1, 2000, "a frame after editorOpen")
        compare(editingAtFirstSwap, false, "closed until the first frame")
        tryVerify(() => main.editing, 2000, "the editor opens after that frame")
        main.frameSwapped.disconnect(onSwap)
        main.editingChanged.disconnect(onEditing)
        verify(swapsAtOpen >= 1, "opened after a frame swap, swaps " + swapsAtOpen)
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

    // A hold on a corner shows its resize handle as the editor's tap does, and the handle resizes the
    // slot; the sheet's Done saves and the handle goes (#69).
    function test_liveHoldShowsTheHandle() {
        const main = makeMain(1024, 600)
        const page = m(main, "chartPage")
        const sheet = find(m(main, "viewEditor"), "slotSheet")
        hold(m(main, "slot-TL"), () => sheet.visible)
        compare(main.editing, false)
        waitForRendering(page)
        const handle = find(page, "handle-TL")
        verify(handle.visible, "the held slot's handle shows")
        const start = draftSlot("TL").sizeMm
        dragBy(main, handle, -Units.mm(20))
        const shrunk = draftSlot("TL").sizeMm
        verify(shrunk < start && shrunk >= 6, "the handle resizes: " + start + " to " + shrunk)
        compare(sheet.sizeMm, shrunk, "the sheet shows it")
        mouseClick(find(sheet, "sheetDone"))
        verify(!sheet.visible)
        verify(!find(page, "handle-TL").visible, "no handle once the sheet is done")
        compare(slotOf(fixture.views.viewJson("shipped-nav"), "TL").sizeMm, shrunk, "Done saved the size")

        // The chart's own buttons hide while a held slot's handle shows, as in the editor, so none
        // lies over the handle; they come back with Done.
        const buttons = ["zoomInButton", "zoomOutButton", "legendButton"]
        for (const b of buttons) verify(find(page, b).visible, b + " shows on the live view")
        hold(m(main, "slot-TR"), () => sheet.visible)
        for (const b of buttons) verify(!find(page, b).visible, b + " hidden while the handle shows")
        mouseClick(find(sheet, "sheetDone"))
        for (const b of buttons) verify(find(page, b).visible, b + " back after Done")

        // Left without Done (Home), a handle drag is dropped.
        hold(m(main, "slot-TL"), () => sheet.visible)
        waitForRendering(page)
        dragBy(main, find(page, "handle-TL"), -Units.mm(10))
        verify(draftSlot("TL").sizeMm < shrunk, "dragged")
        main.page = "home" // as the Home tab does (the bar may have slid off by now)
        verify(!sheet.visible)
        compare(slotOf(fixture.views.viewJson("shipped-nav"), "TL").sizeMm, shrunk, "not saved")
        main.showView("shipped-nav") // as its tab does
        compare(main.page, "view")
        compare(draftSlot("TL").sizeMm, shrunk, "the view shows the saved size")
        verify(!find(page, "handle-TL").visible, "and no handle")
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

    // The on-screen keyboard, standalone at both sizes.
    function makeKeyboard(w, h) {
        const page = createTemporaryObject(pageComp, testCase, { width: w, height: h })
        verify(page, "page")
        return page.keyboard
    }
    function tap(kb, name) { mouseClick(find(kb, name)) }

    function test_keyboardDoneDisabledForWhitespace() {
        Units.windowWidth = 1024
        Units.windowHeight = 600
        const kb = makeKeyboard(1024, 600)
        kb.open("Name", "", 6)
        waitForRendering(kb)
        tap(kb, "key-space"); tap(kb, "key-space"); tap(kb, "key-space")
        compare(kb.text, "   ")
        compare(find(kb, "key-done").enabled, false, "Done needs more than spaces")
    }

    function test_keyboardTypesShiftsAndCaps_data() { return H.sizes() }
    function test_keyboardTypesShiftsAndCaps(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        Units.diagonalIn = data.diagIn
        const kb = makeKeyboard(data.w, data.h)
        verify(!kb.visible)
        kb.open("Name", "", 6)
        verify(kb.visible)
        compare(kb.objectName, "keyboard")
        compare(kb.shift, true)
        waitForRendering(kb)
        const done = find(kb, "key-done")
        compare(done.enabled, false, "Done needs text")
        tap(kb, "key-N"); tap(kb, "key-A"); tap(kb, "key-V")
        compare(kb.text, "Nav")
        compare(find(kb, "keyboardCount").text, "3/6")
        verify(find(kb, "keyboardText").height >= Units.mm(12) - 0.5, "text box 12 mm tall")
        compare(kb.shift, false)
        compare(done.enabled, true)
        tap(kb, "key-space"); tap(kb, "key-shift")
        compare(kb.shift, true)
        tap(kb, "key-X")
        compare(kb.text, "Nav X")
        tap(kb, "key-backspace"); tap(kb, "key-backspace")
        compare(kb.text, "Nav")
        tap(kb, "key-1"); tap(kb, "key-2"); tap(kb, "key-3")
        compare(kb.text, "Nav123")
        tap(kb, "key-4")
        compare(kb.text, "Nav123", "capped at maxChars")
        for (let i = 0; i < 6; ++i) tap(kb, "key-backspace")
        compare(kb.text, "")
        compare(done.enabled, false)
        tap(kb, "key-backspace")
        compare(kb.text, "")

        const room = { x: 0, y: 0, w: kb.width - kb.rightInset, h: kb.height }
        const keys = H.findAll(kb, it => it.isBigButton === true && it.visible)
        verify(keys.length >= 40, "keys: " + keys.length)
        H.checkBigButtons(testCase, Units, kb)
        for (const k of keys) verify(inside(H.box(k, kb), room), k.objectName + " inside width - rightInset")
        for (const n of ["key-1", "key-0", "key-Q", "key-P", "key-A", "key-L", "key-Z", "key-M", "key-shift", "key-backspace", "key-space", "key-cancel", "key-done"])
            find(kb, n)
    }

    // Scrolls every Flickable above `it` so it is on screen, then clicks it.
    function reveal(it) {
        verify(it, "nothing to reveal")
        for (let a = it.parent; a; a = a.parent) {
            if (a.contentItem !== undefined && a.contentY !== undefined) {
                const p = it.mapToItem(a, 0, 0)
                if (p.y < 0 || p.y + it.height > a.height)
                    a.contentY = Math.max(0, Math.min(a.contentHeight - a.height, a.contentY + p.y - Units.mm(2)))
            }
        }
        return it
    }
    function tapShown(it) {
        waitForRendering(it) // a row just shown is laid out on the next frame
        reveal(it)
        waitForRendering(it)
        mouseClick(it)
    }
    // The editor over `id` with its Setup sheet open.
    function openSetup(main, id) {
        main.editView(id)
        mouseClick(m(main, "editorSetup"))
        const sheet = m(main, "setupSheet")
        verify(sheet.visible, "the Setup sheet")
        waitForRendering(sheet)
        return sheet
    }
    // Clears the keyboard's text, then types `text` (capitals with shift).
    function typeInto(kb, text) {
        while (kb.text.length > 0) tap(kb, "key-backspace")
        for (const ch of text) {
            if (ch === " ") { tap(kb, "key-space"); continue }
            const upper = ch.toUpperCase()
            if ((ch === upper) !== kb.shift && upper !== ch.toLowerCase()) tap(kb, "key-shift")
            tap(kb, "key-" + upper)
        }
        compare(kb.text, text)
    }

    function test_setupSheetRowsAndScroll_data() { return H.sizes() }
    function test_setupSheetRowsAndScroll(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        const sheet = openSetup(main, "shipped-big")
        const panel = find(sheet, "setupPanel")
        const room = { x: 0, y: 0, w: main.width - m(main, "tabBar").width, h: m(main, "viewEditor").height }
        const pb = H.box(panel, m(main, "viewEditor"))
        verify(inside(pb, room), "the sheet inside width - rightInset")
        fuzzyCompare(pb.h, room.h, 1, "full height")
        verify(pb.w < room.w - Units.mm(40), "the view shows beside it")
        const names = ["row-name", "row-short", "chart-nav", "chart-fish", "chart-none", "row-layout",
                       "row-favorite", "row-delete", "setupDone"].concat(Icons.names().map(n => "icon-" + n))
        for (const n of names) {
            const b = find(panel, n)
            verify(b.visible, n + " visible")
            verify(b.isBigButton === true, n + " is a BigButton")
            const bb = H.box(b, panel)
            verify(bb.x >= -0.5 && bb.x + bb.w <= panel.width + 0.5, n + " inside the sheet's width")
        }
        H.checkBigButtons(testCase, Units, panel)
        compare(find(panel, "row-name").text, "Name: Big numbers")
        compare(find(panel, "row-short").text, "Short name: Big #")
        compare(find(panel, "row-favorite").text, "Favorite: On")
        compare(find(panel, "row-delete").text, "Delete view")
        verify(find(panel, "icon-hash").highlighted, "the draft's icon")
        verify(!find(panel, "icon-fish").highlighted)
        verify(find(panel, "chart-none").highlighted)
        // Four icons across.
        const row = Icons.names().slice(0, 5).map(n => H.box(find(panel, "icon-" + n), panel))
        for (let i = 1; i < 4; ++i) fuzzyCompare(row[i].y, row[0].y, 0.5)
        verify(row[4].y > row[0].y + 1, "the fifth on the next row")

        const scroller = find(panel, "setupScroller")
        verify(scroller.contentHeight > scroller.height, "it scrolls: " + scroller.contentHeight + " > " + scroller.height)
        const del = find(panel, "row-delete")
        verify(H.box(del, scroller).y + del.height > scroller.height, "Delete starts below the fold")
        reveal(del)
        verify(scroller.contentY > 0, "scrolled")
        const d = H.box(del, scroller)
        verify(d.y >= -0.5 && d.y + d.h <= scroller.height + 0.5, "Delete scrolled into view")

        fixture.draft.chart = "nav"
        verify(!find(panel, "row-layout").visible, "Layout only without a chart")
        mouseClick(find(panel, "setupDone"))
        verify(!sheet.visible, "Done closes the sheet")
        verify(main.editing, "the editor stays open")
    }

    function test_setupKeyboardAndGalleryWorkOnFirstOpen() {
        const main = makeMain(1024, 600, { editorOpen: true, sheet: "setup" })
        const editor = m(main, "viewEditor")
        tryVerify(() => main.editing, 3000, "the editor opens")
        const sheet = find(editor, "setupSheet")
        tryVerify(() => sheet.visible, 3000, "the Setup sheet")
        waitForRendering(sheet)
        editor.setupSheet.editText("name")
        const kb = find(sheet, "keyboard")
        tryVerify(() => kb.visible, 3000, "the keyboard")
        waitForRendering(kb)
        const before = kb.text.length
        tap(kb, "key-A")
        compare(kb.text.length, before + 1)
        tap(kb, "key-cancel")
        verify(!kb.visible)
        editor.setupSheet.openGallery()
        const gallery = find(sheet, "layoutGallery")
        tryVerify(() => gallery.visible, 3000, "the gallery")
        waitForRendering(gallery)
        compare(H.findAll(gallery, it => it.isBigButton === true && it.objectName.startsWith("layout-")).length, 72)
    }

    function test_setupRenamesThroughKeyboard() {
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-nav")
        const kb = find(sheet, "keyboard")
        mouseClick(find(sheet, "row-name"))
        verify(kb.visible, "the keyboard")
        compare(kb.text, "Navigation")
        compare(kb.maxChars, 24)
        waitForRendering(kb)
        typeInto(kb, "Trolling")
        tap(kb, "key-done")
        verify(!kb.visible)
        compare(fixture.draft.name, "Trolling")
        compare(find(sheet, "row-name").text, "Name: Trolling")
        compare(find(sheet, "row-short").text, "Short name: Nav", "the short name is its own field")
        mouseClick(find(sheet, "row-short"))
        verify(kb.visible)
        compare(kb.text, "Nav")
        compare(kb.maxChars, 6)
        typeInto(kb, "Troll")
        tap(kb, "key-done")
        compare(fixture.draft.shortName, "Troll")
        compare(fixture.draft.name, "Trolling")
        verify(sheet.visible, "back on the sheet")
        mouseClick(find(sheet, "setupDone"))
        mouseClick(m(main, "editorDone"))
        const stored = fixture.views.viewJson("shipped-nav")
        compare(stored.name, "Trolling")
        compare(stored.short, "Troll")
    }

    function test_setupChartSwitchAppliesLive() {
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-nav")
        mouseClick(find(sheet, "chart-none"))
        compare(fixture.draft.chart, "none")
        const cells = m(main, "cellPage")
        verify(cells.visible, "the cell page behind the sheet")
        verify(!m(main, "chartPage").visible)
        verify(sheet.visible, "the sheet stays open")
        const shown = H.findAll(cells, it => it.objectName.startsWith("cell-") && it.visible)
        compare(shown.length, fixture.draft.toJson().cells.fields.length, "the draft's cells")
        verify(find(sheet, "chart-none").highlighted)
        mouseClick(find(sheet, "chart-fish"))
        verify(m(main, "chartPage").visible, "the chart back")
        verify(!cells.visible)
        compare(chartStub.mode, "fish")
        mouseClick(find(sheet, "setupDone"))
        mouseClick(m(main, "editorCancel"))
        compare(fixture.draft.chart, "nav")
        compare(fixture.views.viewJson("shipped-nav").chart, "nav")
        compare(chartStub.mode, "nav")
        verify(m(main, "chartPage").visible)
    }

    // Cancel drops every Setup change: name, short name, icon, chart, layout and favorite.
    function test_setupCancelDiscardsEverything() {
        const main = makeMain(1024, 600)
        const before = fixture.views.viewJson("shipped-nav")
        const sheet = openSetup(main, "shipped-nav")
        const kb = find(sheet, "keyboard")
        mouseClick(find(sheet, "row-name"))
        waitForRendering(kb)
        typeInto(kb, "Trolling")
        tap(kb, "key-done")
        mouseClick(find(sheet, "row-short"))
        typeInto(kb, "Troll")
        tap(kb, "key-done")
        tapShown(find(sheet, "icon-fish"))
        tapShown(find(sheet, "chart-none"))
        tapShown(find(sheet, "row-layout"))
        const quad = "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"
        verify(before.cells.layout !== quad, "the quad is a change")
        tapShown(find(sheet, "layout-" + quad))
        tapShown(find(sheet, "row-favorite"))
        const changed = fixture.draft.toJson()
        compare([changed.name, changed.short, changed.icon, changed.chart, changed.cells.layout, changed.favorite],
                ["Trolling", "Troll", "fish", "none", quad, false], "every change made")
        mouseClick(find(sheet, "setupDone"))
        mouseClick(m(main, "editorCancel"))
        const stored = fixture.views.viewJson("shipped-nav")
        compare(stored, before, "nothing stored")
        for (const k of ["name", "short", "icon", "chart", "favorite"]) {
            compare(fixture.draft.toJson()[k], before[k], "draft " + k)
            compare(stored[k], before[k], "stored " + k)
        }
        compare(fixture.draft.layout, before.cells.layout, "draft layout")
        compare(stored.cells.layout, before.cells.layout, "stored layout")
        compare(fixture.draft.toJson(), before)
        compare(chartStub.mode, "nav")
    }

    // The thumbnails stretch to fill each row: the first row's last one ends at the Flow's right edge.
    function test_galleryRowsFillTheWidth_data() { return H.sizes() }
    function test_galleryRowsFillTheWidth(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        Units.diagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        const sheet = openSetup(main, "shipped-big")
        tapShown(find(sheet, "row-layout"))
        const gallery = find(sheet, "layoutGallery")
        tryVerify(() => gallery.visible, 3000, "the gallery")
        waitForRendering(gallery)
        const thumbs = H.findAll(gallery, it => it.isBigButton === true && it.objectName.startsWith("layout-"))
        const boxes = thumbs.map(t => H.box(t, gallery))
        const y0 = Math.min(...boxes.map(b => b.y))
        const row = boxes.filter(b => Math.abs(b.y - y0) < 0.5)
        const left = Math.min(...row.map(b => b.x))
        const right = Math.max(...row.map(b => b.x + b.w))
        const flowW = find(gallery, "galleryScroller").width
        verify(row.length >= 1)
        verify(Math.abs((right - left) - flowW) <= 1, "row " + (right - left) + " vs Flow " + flowW)
    }

    function test_layoutGalleryHas72AndApplies() {
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-big")
        const before = fixture.draft.layout
        tapShown(find(sheet, "row-layout"))
        const gallery = find(sheet, "layoutGallery")
        verify(gallery.visible, "the gallery")
        waitForRendering(gallery)
        const keys = Layouts.gallery().map(g => g.key)
        compare(keys.length, 72)
        const thumbs = H.findAll(gallery, it => it.isBigButton === true && it.objectName.startsWith("layout-"))
        compare(thumbs.length, 72)
        // In gallery order, row by row.
        const byPlace = thumbs.map(t => ({ name: t.objectName, b: H.box(t, gallery) }))
            .sort((a, b) => Math.abs(a.b.y - b.b.y) > 0.5 ? a.b.y - b.b.y : a.b.x - b.b.x)
        compare(byPlace.map(t => t.name), keys.map(k => "layout-" + k))
        for (const t of thumbs) {
            const pic = find(t, "layoutThumb")
            verify(pic.height >= Units.mm(12) - 0.5, t.objectName + " " + pic.height + " tall")
            fuzzyCompare(pic.width / pic.height, 1.6, 0.01)
            compare(t.highlighted, t.objectName === "layout-" + before, t.objectName)
            compare(pic.highlighted, t.highlighted)
        }
        H.checkBigButtons(testCase, Units, gallery)
        const room = { x: 0, y: 0, w: main.width - m(main, "tabBar").width, h: gallery.height }
        verify(inside(H.box(find(gallery, "galleryClose"), gallery), room), "Close inside width - rightInset")
        for (const t of thumbs) {
            const b = H.box(t, gallery)
            verify(b.x >= -0.5 && b.x + b.w <= room.w + 0.5, t.objectName + " inside width - rightInset")
        }
        verify(find(gallery, "galleryScroller").contentHeight > find(gallery, "galleryScroller").height, "it scrolls")

        const quad = "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"
        tapShown(find(gallery, "layout-" + quad))
        verify(!gallery.visible, "a tap closes it")
        compare(fixture.draft.layout, quad)
        verify(sheet.visible, "back on the sheet")
        const cells = H.findAll(m(main, "cellPage"), it => it.objectName.startsWith("cell-") && it.visible)
        compare(cells.length, 4, "four cells on the page")

        tapShown(find(sheet, "row-layout"))
        verify(find(gallery, "layout-" + quad).highlighted)
        mouseClick(find(gallery, "galleryClose"))
        verify(!gallery.visible)
        compare(fixture.draft.layout, quad)
    }

    function test_favoriteRowNotesFullBar() {
        const main = makeMain(1024, 600)
        compare(fixture.views.favoriteCapacity, 5)
        for (let i = 0; i < 2; ++i) fixture.views.setFavorite(fixture.views.add(), true)
        const sixth = fixture.views.add()
        fixture.views.setFavorite(sixth, true)
        verify(!fixture.views.onTabBar(sixth))
        let sheet = openSetup(main, sixth)
        const row = find(sheet, "row-favorite")
        compare(row.text, "Favorite: On")
        const note = find(sheet, "favoriteNote")
        verify(note.visible, "the note")
        compare(note.text, "Not on tab bar (full)")
        tapShown(row)
        compare(fixture.draft.favorite, false)
        compare(row.text, "Favorite: Off")
        verify(!note.visible, "no note when off")
        mouseClick(find(sheet, "setupDone"))
        mouseClick(m(main, "editorCancel"))

        // A favorite on the bar has no note.
        sheet = openSetup(main, "shipped-fish")
        verify(!find(sheet, "favoriteNote").visible)
    }

    function test_deleteFromSetupGoesHome() {
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-fish")
        const del = find(sheet, "row-delete")
        tapShown(del)
        const question = find(sheet, "setupDeleteQuestion")
        verify(question.visible)
        compare(question.text, "Delete Fishing?")
        tapShown(find(sheet, "setupKeep"))
        verify(!question.visible)
        compare(fixture.views.count, 3)
        tapShown(del)
        tapShown(find(sheet, "setupDeleteYes"))
        compare(fixture.views.count, 2)
        compare(fixture.views.indexOf("shipped-fish"), -1)
        compare(main.editing, false)
        compare(main.page, "home")
        verify(!sheet.visible)
        compare(fixture.views.currentId, "shipped-big", "the neighbour")
        compare(fixture.draft.id, fixture.views.currentId)

        // A new view deleted from its own Setup: the view current before New is current again.
        fixture.views.currentId = "shipped-nav"
        waitForRendering(m(main, "homePage")) // the tiles move up after the delete
        mouseClick(m(main, "tile-new"))
        verify(main.editingNew)
        verify(sheet.visible)
        compare(fixture.views.count, 3)
        tapShown(del)
        tapShown(find(sheet, "setupDeleteYes"))
        compare(fixture.views.count, 2)
        compare(fixture.views.currentId, "shipped-nav", "the view current before New")
        compare(fixture.draft.id, "shipped-nav")
        compare(main.page, "home")
        compare(main.editing, false)
        verify(!main.editingNew)
    }

    // The note before Done: the draft is a favorite, the stored view not yet, and the bar is full.
    function test_favoriteNoteEstimatedBeforeDone() {
        const main = makeMain(1024, 600)
        compare(fixture.views.favoriteCapacity, 5)
        for (let i = 0; i < 2; ++i) fixture.views.setFavorite(fixture.views.add(), true)
        compare(fixture.views.tabViews.length, 5)
        const plain = fixture.views.add()
        verify(!fixture.views.viewJson(plain).favorite)
        const sheet = openSetup(main, plain)
        const note = find(sheet, "favoriteNote")
        compare(find(sheet, "row-favorite").text, "Favorite: Off")
        verify(!note.visible)
        tapShown(find(sheet, "row-favorite"))
        compare(fixture.draft.favorite, true)
        verify(!fixture.views.viewJson(plain).favorite, "not stored before Done")
        verify(note.visible, "the note before Done")
        compare(note.text, "Not on tab bar (full)")
    }

    // A slot or cell sheet open: the floating buttons hide, and the sheet's Done is clear of them.
    function test_sheetsHideTheFloatingButtons_data() { return H.sizes() }
    function test_sheetsHideTheFloatingButtons(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        const editor = m(main, "viewEditor")
        const floating = ["editorSetup", "editorDone", "editorCancel"].map(n => m(main, n))
        const check = (sheet, what) => {
            verify(sheet.visible, what)
            waitForRendering(sheet)
            const done = find(sheet, "sheetDone")
            verify(done.visible, what + " Done visible")
            for (const b of floating) {
                verify(!b.visible, b.objectName + " hidden under the " + what)
                verify(!(b.visible && H.overlaps(b, done, editor)), b.objectName + " clear of the " + what + " Done")
            }
            mouseClick(done)
            verify(!sheet.visible)
            for (const b of floating) verify(b.visible, b.objectName + " back")
        }
        main.editView("shipped-nav")
        mouseClick(m(main, "slot-TR"))
        check(find(editor, "slotSheet"), "slot sheet")
        mouseClick(m(main, "editorCancel"))

        main.editView("shipped-big")
        fixture.draft.layout = "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"
        waitForRendering(m(main, "cellPage"))
        mouseClick(m(main, "cell-3"))
        check(find(editor, "cellSheet"), "cell sheet")
        mouseClick(m(main, "editorCancel"))
    }

    function test_lastViewSetupDeleteDisabled() {
        verify(fixture.views.remove("shipped-fish"))
        verify(fixture.views.remove("shipped-big"))
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-nav")
        const del = find(sheet, "row-delete")
        verify(!del.enabled)
        compare(del.text, "Can't delete the last view")
        tapShown(del)
        verify(!find(sheet, "setupDeleteQuestion").visible)
        compare(fixture.views.count, 1)
        verify(main.editing)
    }

    function test_newViewOpensEditorWithSetup() {
        const main = makeMain(1024, 600)
        mouseClick(m(main, "tab-home"))
        mouseClick(m(main, "tile-new"))
        verify(main.editing)
        const sheet = m(main, "setupSheet")
        verify(sheet.visible, "Setup open on a new view")
        compare(find(sheet, "row-name").text, "Name: View 4")
        mouseClick(find(sheet, "setupDone"))
        verify(!sheet.visible)
        verify(main.editing)
        mouseClick(m(main, "editorCancel"))
        compare(fixture.views.count, 3)
        // Edit from Home does not open Setup.
        editFromHome(main, "shipped-nav")
        verify(!sheet.visible)
    }

    function test_iconGridPicks() {
        const main = makeMain(1024, 600)
        const sheet = openSetup(main, "shipped-nav")
        tapShown(find(sheet, "icon-fish"))
        compare(fixture.draft.icon, "fish")
        verify(find(sheet, "icon-fish").highlighted)
        verify(!find(sheet, "icon-compass").highlighted)
        mouseClick(find(sheet, "setupDone"))
        mouseClick(m(main, "editorDone"))
        compare(fixture.views.viewJson("shipped-nav").icon, "fish")
        const tab = m(main, "tab-view-shipped-nav")
        const icons = H.findAll(tab, it => it.sourceSize !== undefined && it.name !== undefined)
        compare(icons.length, 1)
        compare(icons[0].name, "fish")
    }

    function test_keyboardCancelKeepsOldText() {
        const kb = makeKeyboard(1024, 600)
        const cancelled = createTemporaryObject(spyComp, testCase, { target: kb, signalName: "cancelled" })
        const accepted = createTemporaryObject(spyComp, testCase, { target: kb, signalName: "accepted" })
        kb.open("Name", "Old", 24)
        compare(kb.shift, false)
        compare(kb.title, "Name")
        compare(kb.maxChars, 24)
        waitForRendering(kb)
        tap(kb, "key-backspace"); tap(kb, "key-X")
        compare(kb.text, "Olx")
        tap(kb, "key-cancel")
        compare(cancelled.count, 1)
        compare(accepted.count, 0)
        compare(kb.text, "Old")
        verify(!kb.visible)

        kb.open("Name", "Old", 24)
        tap(kb, "key-shift"); tap(kb, "key-Z")
        tap(kb, "key-done")
        compare(accepted.count, 1)
        compare(accepted.signalArguments[0][0], "OldZ")
        verify(!kb.visible)

        kb.open("Name", "0123456789", 6)
        compare(kb.text, "012345")
        compare(find(kb, "keyboardCount").text, "6/6")
        tap(kb, "key-cancel")
        compare(kb.text, "012345")
    }
}
