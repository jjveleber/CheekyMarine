import QtQuick
import QtTest
import CheekyMarine
import "Helpers.js" as H

// The app shell over the saved views: the favorite tabs and the house tab, the Home page of
// tiles and its tile menu, the pages beside the bar, and the shell tests that need Main (lock,
// banner, record dot).
TestCase {
    id: testCase
    name: "Views"
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
        property var zooms: [] // zoomBy calls: log2 deltas
        property var target: undefined // what targetAt resolves
        function targetAt(p, r) { return target }
        function selectAt(p, r) {}
        function clearTarget() { aisSelection = ({}) }
        function zoomIn() {}
        function zoomOut() {}
        function zoomBy(d) { zooms.push(d) }
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
            property int gestures: 0
            property int moves: 0
            property var scales: [] // scaleBy factors
            onUserGesture: gestures++
            function moveBy(p) { moves++ }
            function scaleBy(f, p) { scales.push(f) }
        }
    }
    Component { id: mainComp; Main {} }
    Component { id: splashComp; Splash {} }

    function init() {
        failOnWarning(/.*/)
        fixture.reset()
        chartStub.follow = true
        chartStub.mode = "nav"
        chartStub.zooms = []
        chartStub.target = undefined
        chartStub.fishAvailable = true
        Units.windowWidth = 1280
        Units.windowHeight = 800
        Units.diagonalIn = 10.1
    }

    function cleanup() { Theme.palette = "day" }

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
        waitForRendering(main.contentItem) // the tab column lays out its tabs on the next frame
        return main
    }
    function item(main, name) {
        const it = H.byName(main.contentItem, name)
        verify(it, name)
        return it
    }
    function viewTabs(main) {
        return H.findAll(main.contentItem, it => it.isBigButton === true && it.objectName.startsWith("tab-view-"))
    }
    function tiles(main) {
        return H.findAll(item(main, "homePage"), it => it.isBigButton === true && it.objectName.startsWith("tile-"))
    }
    function goHome(main) {
        mouseClick(item(main, "tab-home"))
        compare(main.page, "home")
        const home = item(main, "homePage")
        verify(home.visible)
        waitForRendering(home)
        return home
    }
    // Scrolls every Flickable above `it` so it is on screen, then clicks it.
    function tap(it) {
        verify(it, "nothing to tap")
        for (let a = it.parent; a; a = a.parent) {
            if (a.contentItem !== undefined && a.contentY !== undefined) {
                const p = it.mapToItem(a, 0, 0)
                if (p.y < 0 || p.y + it.height > a.height)
                    a.contentY = Math.max(0, Math.min(a.contentHeight - a.height, a.contentY + p.y - Units.mm(2)))
            }
        }
        mouseClick(it)
    }
    // A mouse hold on `it` until `done()` holds (the hold is 0.6 s; up to 3 s allowed), then release.
    function hold(it, done) {
        verify(it, "nothing to hold")
        mousePress(it)
        tryVerify(done, 3000, "the hold took effect")
        mouseRelease(it)
    }
    // The tile menu open for the view `id`.
    function menuFor(main, id) {
        const menu = item(main, "tileMenu")
        if (!(menu.visible && menu.viewId === id)) {
            if (menu.visible) mouseClick(H.byName(menu, "menu-close"))
            hold(item(main, "tile-" + id), () => menu.visible)
        }
        verify(menu.visible, "menu open")
        compare(menu.viewId, id)
        compare(main.page, "home", "a hold is not a tap")
        waitForRendering(menu)
        return menu
    }
    function viewOrder() {
        const out = []
        for (const id of ["shipped-nav", "shipped-fish", "shipped-big"]) out[fixture.views.indexOf(id)] = id
        return out
    }

    function test_mainConstructs_data() { return H.sizes() }
    function test_mainConstructs(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        compare(Units.windowWidth, data.w)
        compare(Units.windowHeight, data.h)
        fuzzyCompare(Units.pxPerMm, data.ppm, 0.001)
        compare(main.pages, ["home", "view", "tracks", "settings", "about"])
        // All pages exist in the stack, so the walk covers them.
        for (const n of ["homePage", "chartPage", "cellPage", "tracksPage", "settingsPage", "aboutPage", "tabBar", "splash"])
            verify(H.byName(main.contentItem, n), n)
        H.checkBigButtons(testCase, Units, main.contentItem)
        const bar = item(main, "tabBar")
        tryVerify(() => {
            const b = H.box(bar, main.contentItem)
            return b.x >= -0.5 && b.y >= -0.5 && Math.abs(b.x + b.w - main.width) < 0.5 && b.y + b.h <= main.height + 0.5
        }, 1000, "tab bar inside the window, on the right edge")
        compare(viewTabs(main).map(t => t.objectName).sort(),
                ["tab-view-shipped-big", "tab-view-shipped-fish", "tab-view-shipped-nav"])
        verify(item(main, "tab-home").isBigButton)
    }

    // Five favorites fit at both sizes on the 10.1 in panel (eight on the 13 in one: more mm of
    // height); one more is a plain view whose tile says so.
    function test_favoriteTabsFollowCapacity_data() { return H.sizes() }
    function test_favoriteTabsFollowCapacity(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        const cap = data.diagIn > 10.1 ? 8 : 5
        compare(fixture.views.favoriteCapacity, cap)
        for (let i = 0; i < cap - 3; ++i) fixture.views.setFavorite(fixture.views.add(), true)
        compare(viewTabs(main).length, cap)
        const sixth = fixture.views.add()
        fixture.views.setFavorite(sixth, true)
        compare(viewTabs(main).length, cap)
        compare(H.byName(main.contentItem, "tab-view-" + sixth), null)
        verify(!fixture.views.onTabBar(sixth))
        const bar = item(main, "tabBar")
        waitForRendering(bar)
        for (const b of H.findAll(bar, it => it.isBigButton === true)) {
            const p = H.box(b, main.contentItem)
            verify(p.y >= -0.5 && p.y + p.h <= main.height + 0.5,
                   b.objectName + " at " + Math.round(p.y) + ".." + Math.round(p.y + p.h) + ", window " + main.height)
        }
        goHome(main)
        const note = H.byName(item(main, "tile-" + sixth), "tileNote")
        verify(note && note.visible, "the note on the sixth tile")
        compare(note.text, "Not on tab bar (full)")
        for (const id of ["shipped-nav", "shipped-fish", "shipped-big"])
            verify(!H.byName(item(main, "tile-" + id), "tileNote").visible, id + " is on the tab bar")
    }

    // A small panel diagonal leaves the column fewer favorite tabs; every tab and control stays
    // inside the window at full size.
    function test_tabBarFitsTheWindow_data() {
        let out = []
        for (const s of H.sizes())
            for (const d of [7, 10.1])
                out.push({ tag: s.tag + " " + d + " in", w: s.w, h: s.h, diag: d })
        return out
    }
    function test_tabBarFitsTheWindow(data) {
        fixture.settings.panelDiagonalIn = data.diag
        const main = makeMain(data.w, data.h)
        compare(Units.diagonalIn, data.diag)
        const bar = item(main, "tabBar")
        waitForRendering(bar)
        const capacity = PanelMath.favoriteCapacity(bar.height / Units.pxPerMm)
        compare(fixture.views.favoriteCapacity, capacity)
        compare(viewTabs(main).length, Math.min(3, capacity))
        const buttons = H.findAll(bar, it => it.isBigButton === true)
        compare(buttons.length, Math.min(3, capacity) + 3)
        H.checkBigButtons(testCase, Units, bar)
        for (const t of buttons.filter(b => b.objectName.startsWith("tab-")))
            verify(t.width >= Units.mm(15) - 0.5 && t.height >= Units.mm(15) - 0.5, t.objectName)
        for (const b of buttons) {
            const p = b.mapToItem(main.contentItem, 0, 0)
            verify(p.y >= 0 && p.y + b.height <= main.height + 0.5,
                   b.objectName + " at " + Math.round(p.y) + ".." + Math.round(p.y + b.height) + ", window " + main.height)
        }
    }

    function test_tabsAre15mmAndShowIconAndShortName() {
        const main = makeMain(1024, 600)
        const want = { "shipped-nav": ["compass", "Nav"], "shipped-fish": ["fish", "Fish"], "shipped-big": ["hash", "Big #"] }
        const tabs = viewTabs(main).concat([item(main, "tab-home")])
        compare(tabs.length, 4)
        for (const t of tabs) {
            verify(Math.abs(t.width - Units.mm(15)) < 0.5 && Math.abs(t.height - Units.mm(15)) < 0.5,
                   t.objectName + " is " + t.width + "x" + t.height)
            const icons = H.findAll(t, it => it.sourceSize !== undefined && it.name !== undefined)
            compare(icons.length, 1, t.objectName + " has one icon")
            tryCompare(icons[0], "status", Image.Ready)
            if (t.objectName === "tab-home") {
                compare(icons[0].name, "home")
                continue
            }
            const w = want[t.objectName.slice("tab-view-".length)]
            compare(icons[0].name, w[0])
            fuzzyCompare(icons[0].width, Units.mm(6.5), 0.5)
            const labels = H.findAll(t, it => it.text === w[1] && it.font !== undefined && it.isBigButton !== true)
            compare(labels.length, 1, t.objectName + " shows " + w[1])
            fuzzyCompare(labels[0].font.pixelSize, Units.mm(2.9), 0.5)
            verify(icons[0].mapToItem(t, 0, 0).y + icons[0].height <= labels[0].mapToItem(t, 0, 0).y + 0.5, "icon over the name")
        }
        const bar = item(main, "tabBar")
        tryVerify(() => Math.abs(bar.mapToItem(main.contentItem, 0, 0).x + bar.width - main.width) < 0.5,
                  1000, "tab bar on the right edge")
    }

    function test_tapTabShowsView() {
        const main = makeMain(1024, 600)
        mouseClick(item(main, "tab-view-shipped-big"))
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-big")
        verify(item(main, "cellPage").visible)
        verify(item(main, "tab-view-shipped-big").highlighted)
        verify(!item(main, "tab-view-shipped-nav").highlighted)
        verify(!item(main, "tab-home").highlighted)
        mouseClick(item(main, "tab-view-shipped-fish"))
        compare(chartStub.mode, "fish")
        verify(item(main, "chartPage").visible)
        verify(item(main, "tab-view-shipped-fish").highlighted)
        verify(!item(main, "tab-view-shipped-big").highlighted)
    }

    function test_tabHoldEmitsViewHeldNotSelected() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        const held = createTemporaryObject(spyComp, testCase, { target: bar, signalName: "viewHeld" })
        const selected = createTemporaryObject(spyComp, testCase, { target: bar, signalName: "viewSelected" })
        const touched = createTemporaryObject(spyComp, testCase, { target: bar, signalName: "touched" })
        hold(item(main, "tab-view-shipped-fish"), () => held.count > 0)
        compare(held.count, 1)
        compare(held.signalArguments[0][0], "shipped-fish")
        compare(selected.count, 0)
        mouseClick(item(main, "editorCancel")) // the hold opened the editor (test_holdFavoriteTabOpensEditor)
        mouseClick(item(main, "tab-home"))
        mouseClick(item(main, "paletteButton"))
        compare(touched.count, 3, "every bar button press")
    }
    Component { id: spyComp; SignalSpy {} }

    // Hold a favorite tab 0.6 s: the editor on that view (spec 6.9); a plain tap still just shows it.
    function test_holdFavoriteTabOpensEditor() {
        const main = makeMain(1024, 600)
        compare(fixture.views.currentId, "shipped-nav")
        const tab = item(main, "tab-view-shipped-fish")
        const t0 = Date.now()
        mousePress(tab)
        verify(!main.editing, "not before the hold time")
        tryVerify(() => main.editing, 3000, "the 0.6 s hold opens the editor")
        verify(Date.now() - t0 >= 590, "after the hold time: " + (Date.now() - t0))
        mouseRelease(tab)
        verify(main.editing, "the editor")
        compare(fixture.views.currentId, "shipped-fish")
        compare(fixture.draft.id, "shipped-fish")
        compare(main.page, "view")
        verify(!item(main, "setupSheet").visible, "a hold opens the editor, not Setup")
        mouseClick(item(main, "editorCancel"))
        compare(main.editing, false)

        mouseClick(item(main, "tab-view-shipped-big"))
        compare(fixture.views.currentId, "shipped-big")
        compare(main.page, "view")
        compare(main.editing, false, "a tap just shows it")
        mouseClick(item(main, "tab-view-shipped-fish"))
        compare(fixture.views.currentId, "shipped-fish")
        compare(main.editing, false)
    }

    // A drag that starts on a view tab and runs over the map neither pans the map (Follow stays on)
    // nor presses the tab: the map's handlers never take over from an item.
    function test_dragFromTabDoesNotPanTheMap() {
        const main = makeMain(1024, 600)
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-nav")
        verify(item(main, "tabBar").shown)
        const tab = item(main, "tab-view-shipped-fish")
        const x0 = tab.width / 2, y0 = tab.height / 2
        mousePress(tab, x0, y0)
        for (let i = 1; i <= 15; ++i)
            mouseMove(tab, x0 - Units.mm(i), y0, 10, Qt.LeftButton)
        wait(100)
        mouseRelease(tab, x0 - Units.mm(15), y0)
        compare(main.chartMap.moves, 0, "no pan")
        compare(main.chartMap.gestures, 0, "no gesture")
        compare(chartStub.follow, true, "Follow stays on")
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-nav", "the tab was not pressed")
        verify(!main.editing)
    }

    // The touch version of the same drag.
    function test_touchDragFromTabDoesNotPanTheMap() {
        const main = makeMain(1024, 600)
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-nav")
        verify(item(main, "tabBar").shown)
        const tab = item(main, "tab-view-shipped-fish")
        const x0 = tab.width / 2, y0 = tab.height / 2
        touchEvent(main).press(0, tab, x0, y0).commit()
        for (let i = 1; i <= 15; ++i)
            touchEvent(main).move(0, tab, x0 - Units.mm(i), y0).commit()
        wait(100)
        touchEvent(main).release(0, tab, x0 - Units.mm(15), y0).commit()
        compare(main.chartMap.moves, 0, "no pan")
        compare(main.chartMap.gestures, 0, "no gesture")
        compare(chartStub.follow, true, "Follow stays on")
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-nav", "the tab was not pressed")
        verify(!main.editing)
    }

    function test_nonFavoriteViewHighlightsHouse() {
        const main = makeMain(1024, 600)
        const id = fixture.views.add()
        goHome(main)
        verify(item(main, "tab-home").highlighted, "Home highlights the house")
        tap(item(main, "tile-" + id))
        compare(main.page, "view")
        compare(fixture.views.currentId, id)
        verify(item(main, "tab-home").highlighted)
        for (const t of viewTabs(main)) verify(!t.highlighted, t.objectName)
        mouseClick(item(main, "tab-view-shipped-nav"))
        verify(!item(main, "tab-home").highlighted)
    }

    function test_homeTilesInOrder_data() { return H.sizes() }
    function test_homeTilesInOrder(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        const home = goHome(main)
        const order = ["tile-shipped-nav", "tile-shipped-fish", "tile-shipped-big", "tile-new", "tile-tracks", "tile-settings", "tile-about"]
        const all = tiles(main)
        compare(all.map(t => t.objectName).sort(), order.slice().sort())
        const boxes = order.map(n => H.box(item(main, n), home))
        for (let i = 1; i < boxes.length; ++i) {
            const a = boxes[i - 1], b = boxes[i]
            verify((Math.abs(a.y - b.y) < 0.5 && b.x > a.x) || b.y >= a.y + a.h - 0.5, order[i] + " comes after " + order[i - 1])
        }
        const cols = 3 // at both sizes on the 10.1 in panel
        compare(home.columns, cols)
        compare(boxes.filter(b => Math.abs(b.y - boxes[0].y) < 0.5).length, cols, "tiles in the first row")
        for (let i = 0; i < boxes.length; ++i) {
            verify(boxes[i].w >= Units.mm(40) - 0.5 && boxes[i].h >= Units.mm(30) - 0.5,
                   order[i] + " is " + Math.round(boxes[i].w / Units.pxPerMm) + "x" + Math.round(boxes[i].h / Units.pxPerMm) + " mm")
            verify(boxes[i].x + boxes[i].w <= home.width - home.rightInset + 0.5, order[i] + " clear of the bar")
        }
        for (const n of order.slice(0, 3)) {
            const thumb = H.byName(item(main, n), "viewThumb")
            verify(thumb && thumb.visible, n + " thumb")
            verify(thumb.height >= Units.mm(12) - 0.5, n + " thumb is " + thumb.height)
        }
        const stars = order.slice(0, 3).map(n => H.byName(item(main, n), "tileStar"))
        verify(stars.every(s => s && s.visible && s.name === "star"), "the shipped views are favorites")
        compare(H.findAll(item(main, "tile-tracks"), it => it.name === "map").length, 1)
        compare(H.findAll(item(main, "tile-settings"), it => it.name === "settings").length, 1)
        compare(item(main, "tile-new").text, "+ New view")
    }

    // A page with less than 3 x 40 mm free beside the bar (no shipped window and diagonal gives one:
    // even 7 in at 1024x600 leaves 43 mm a column) lays the tiles out in two columns.
    Component { id: homeComp; HomePage {} }
    function test_homeTwoColumnsWhenNarrow_data() { return H.sizes() }
    function test_homeTwoColumnsWhenNarrow(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        Units.diagonalIn = data.diagIn
        const home = createTemporaryObject(homeComp, testCase, {
            width: Units.mm(17 + 6 + 110), height: data.h, rightInset: Units.mm(17), views: fixture.views })
        verify(home, "HomePage")
        waitForRendering(home)
        compare(home.columns, 2)
        const order = ["tile-shipped-nav", "tile-shipped-fish", "tile-shipped-big", "tile-new"]
        const boxes = order.map(n => H.box(H.byName(home, n), home))
        verify(Math.abs(boxes[0].y - boxes[1].y) < 0.5 && boxes[1].x > boxes[0].x, "first row: two tiles")
        verify(boxes[2].y >= boxes[0].y + boxes[0].h - 0.5 && Math.abs(boxes[2].x - boxes[0].x) < 0.5, "third tile starts row two")
        for (let i = 0; i < boxes.length; ++i) {
            verify(boxes[i].w >= Units.mm(40) - 0.5, order[i] + " is " + boxes[i].w)
            verify(boxes[i].x + boxes[i].w <= home.width - home.rightInset + 0.5, order[i] + " clear of the bar")
        }
    }

    // A view switch loads the draft once.
    function test_viewSwitchLoadsDraftOnce() {
        const main = makeMain(1024, 600)
        const loads = createTemporaryObject(spyComp, testCase, { target: fixture.draft, signalName: "idChanged" })
        mouseClick(item(main, "tab-view-shipped-fish"))
        compare(fixture.draft.id, "shipped-fish")
        compare(loads.count, 1, "tab")
        goHome(main)
        tap(item(main, "tile-shipped-big"))
        compare(fixture.draft.id, "shipped-big")
        compare(loads.count, 2, "tile")
        goHome(main)
        tap(item(main, "tile-new"))
        compare(loads.count, 3, "new view")
    }

    // The thumbnail draws the view: a chart kind's on slots over its chart colour, a cell view's cells.
    function test_viewThumbDrawsTheView() {
        const main = makeMain(1024, 600)
        goHome(main)
        const nav = H.byName(item(main, "tile-shipped-nav"), "viewThumb")
        compare(nav.color, Theme.thumbNav)
        compare(H.findAll(nav, it => it.objectName === "thumbSlot" && it.visible).length, 2) // TL and TR
        compare(H.byName(item(main, "tile-shipped-fish"), "viewThumb").color, Theme.thumbFish)
        const big = H.byName(item(main, "tile-shipped-big"), "viewThumb")
        compare(big.color, Theme.background)
        const cells = H.findAll(big, it => it.objectName === "thumbCell" && it.visible)
        compare(cells.length, 2)
        verify(Math.abs(cells[0].width - (big.width - 6) / 2) < 1, "two columns, 2 px gaps: " + cells[0].width)
    }

    function test_homeTileTapShowsView() {
        const main = makeMain(1024, 600)
        goHome(main)
        tap(item(main, "tile-shipped-fish"))
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-fish")
        compare(chartStub.mode, "fish")
        verify(item(main, "chartPage").visible)
        verify(item(main, "tab-view-shipped-fish").highlighted)
        verify(!item(main, "tab-home").highlighted)
    }

    function test_homeTilesOpenTracksSettingsAbout() {
        const main = makeMain(1024, 600)
        goHome(main)
        tap(item(main, "tile-tracks"))
        compare(main.page, "tracks")
        verify(item(main, "tracksPage").visible)
        verify(item(main, "recordButton").visible)
        goHome(main)
        tap(item(main, "tile-settings"))
        compare(main.page, "settings")
        verify(item(main, "settingsPage").visible)
        waitForRendering(item(main, "settingsPage"))
        tap(item(main, "aboutButton"))
        compare(main.page, "about")
        goHome(main)
        tap(item(main, "tile-about"))
        compare(main.page, "about")
        verify(item(main, "aboutPage").visible)
        mouseClick(item(main, "aboutBack"))
        compare(main.page, "home")
    }

    function test_tileMenuActions() {
        const main = makeMain(1024, 600)
        goHome(main)
        let menu = menuFor(main, "shipped-fish")
        H.checkBigButtons(testCase, Units, menu)
        mouseClick(H.byName(menu, "menu-moveRight"))
        compare(viewOrder(), ["shipped-nav", "shipped-big", "shipped-fish"])

        menu = menuFor(main, "shipped-fish")
        const fav = H.byName(menu, "menu-favorite")
        compare(fav.text, "Favorite off")
        mouseClick(fav)
        verify(!fixture.views.viewJson("shipped-fish").favorite)
        verify(!H.byName(item(main, "tile-shipped-fish"), "tileStar").visible, "star gone")
        compare(H.byName(main.contentItem, "tab-view-shipped-fish"), null)
        menu = menuFor(main, "shipped-fish")
        compare(H.byName(menu, "menu-favorite").text, "Favorite on")

        mouseClick(H.byName(menu, "menu-duplicate"))
        compare(fixture.views.count, 4)
        const dup = tiles(main).filter(t => t.name === "Fishing 2")
        compare(dup.length, 1, "a tile named Fishing 2")
        const dupId = dup[0].objectName.slice("tile-".length)

        menu = menuFor(main, dupId)
        mouseClick(H.byName(menu, "menu-delete"))
        const ask = H.byName(menu, "menu-deleteQuestion")
        verify(ask.visible)
        compare(ask.text, "Delete Fishing 2?")
        mouseClick(H.byName(menu, "menu-keep"))
        compare(fixture.views.count, 4)
        verify(H.byName(main.contentItem, "tile-" + dupId), "still there")

        menu = menuFor(main, dupId)
        mouseClick(H.byName(menu, "menu-delete"))
        mouseClick(H.byName(menu, "menu-deleteYes"))
        compare(fixture.views.count, 3)
        compare(fixture.views.indexOf(dupId), -1)
        compare(H.byName(main.contentItem, "tile-" + dupId), null)
        verify(!menu.visible)
        compare(main.page, "home")
    }

    // A tap outside the menu closes it and does nothing else.
    function test_tileMenuClosesOnOutsideTap() {
        const main = makeMain(1024, 600)
        const home = goHome(main)
        const menu = menuFor(main, "shipped-nav")
        mouseClick(home, Units.mm(2), Units.mm(2))
        verify(!menu.visible)
        compare(main.page, "home")
    }

    // Review Focus 4: there is always at least one view.
    function test_lastViewCannotBeDeleted() {
        verify(fixture.views.remove("shipped-fish"))
        verify(fixture.views.remove("shipped-big"))
        compare(fixture.views.count, 1)
        const main = makeMain(1024, 600)
        goHome(main)
        const menu = menuFor(main, "shipped-nav")
        const del = H.byName(menu, "menu-delete")
        verify(!del.enabled)
        compare(del.text, "Can't delete the last view")
        mouseClick(del)
        compare(fixture.views.count, 1)
        verify(!H.byName(menu, "menu-deleteQuestion").visible)
    }

    function test_newViewTileAddsAndShows() {
        const main = makeMain(1024, 600)
        goHome(main)
        tap(item(main, "tile-new"))
        compare(fixture.views.count, 4)
        compare(fixture.views.viewJson(fixture.views.currentId).name, "View 4")
        compare(fixture.draft.name, "View 4")
        compare(main.page, "view")
        verify(item(main, "chartPage").visible)
    }

    // A New whose insert fails opens no editor: the shown view stays and nothing can delete it.
    function test_newViewInsertFailureOpensNoEditor() {
        const main = makeMain(1024, 600)
        goHome(main)
        fixture.failViewInserts(true)
        ignoreWarning(/views: insert failed/)
        tap(item(main, "tile-new"))
        fixture.failViewInserts(false)
        compare(fixture.views.count, 3)
        compare(fixture.views.currentId, "shipped-nav")
        verify(!main.editing, "no editor")
        verify(!main.editingNew)
        compare(main.page, "home")
    }

    // Every page keeps its controls left of the bar.
    function test_pagesHonourRightInset_data() {
        let out = []
        for (const s of H.sizes())
            for (const p of [["tracks", "tracksPage"], ["settings", "settingsPage"], ["about", "aboutPage"], ["home", "homePage"]])
                out.push({ tag: s.tag + " " + p[0], w: s.w, h: s.h, diagIn: s.diagIn, page: p[0], item: p[1] })
        return out
    }
    function test_pagesHonourRightInset(data) {
        fixture.addTrack(1.7e9)
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        main.page = data.page
        const page = item(main, data.item)
        verify(page.visible)
        waitForRendering(page)
        const bar = item(main, "tabBar")
        fuzzyCompare(page.rightInset, bar.width, 0.5)
        fuzzyCompare(page.width, main.width, 0.5)
        const right = page.width - page.rightInset
        const buttons = H.findAll(page, it => it.isBigButton === true)
        verify(buttons.length > 0)
        for (const b of buttons) {
            const p = H.box(b, page)
            verify(p.x + p.w <= right + 0.5, b.objectName + " (" + b.text + ") ends at " + Math.round(p.x + p.w) + ", bar at " + Math.round(right))
        }
    }

    function test_tabsSwitchPagesAndPaletteCycles() {
        const main = makeMain(1024, 600)
        compare(main.page, "view")
        verify(H.byName(main.contentItem, "tab-tracks") === null, "no Tracks tab")
        mouseClick(item(main, "tab-home"))
        compare(main.page, "home")
        mouseClick(item(main, "tab-view-shipped-nav"))
        compare(main.page, "view")
        verify(item(main, "chartPage").visible)
        compare(fixture.settings.paletteMode, "auto")
        const pal = item(main, "paletteButton")
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "day")
        mouseClick(pal)
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "night")
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "auto")
    }

    function test_mainShowsCellPageForNoneViews() {
        const main = makeMain(1024, 600)
        const chart = item(main, "chartPage"), cells = item(main, "cellPage")
        verify(chart.visible)
        verify(!cells.visible)
        compare(chartStub.mode, "nav")
        fixture.views.currentId = "shipped-big"
        compare(fixture.draft.chart, "none")
        verify(cells.visible)
        verify(!chart.visible)
        fixture.views.currentId = "shipped-nav"
        verify(chart.visible)
        verify(!cells.visible)
        compare(chartStub.mode, "nav")
        fixture.views.currentId = "shipped-fish"
        verify(chart.visible)
        compare(chartStub.mode, "fish")
    }

    function test_mainBannerFollowsSchemaMismatch() {
        const main = makeMain(1024, 600)
        const banner = item(main, "noDataBanner")
        verify(banner.visible)
        compare(banner.text, "No data from N2K")
        fixture.appInfo.setSchemaMismatch(2)
        compare(banner.text, "Daemon too new or too old")
        fixture.setVessel(3, 2)
        verify(!banner.visible)
    }

    function test_lockSwallowsTouchesAndLongPressUnlocks() {
        const main = makeMain(1024, 600)
        const overlay = item(main, "lockOverlay")
        verify(!overlay.visible, "no overlay while unlocked")
        mouseClick(item(main, "lockButton"))
        verify(fixture.touchLock.locked, "the Lock button locks")
        verify(overlay.visible)
        mouseClick(item(main, "tab-home"))
        compare(main.page, "view")
        mouseClick(item(main, "paletteButton"))
        compare(fixture.settings.paletteMode, "auto")
        // A mouse drag and a wheel turn on the chart stop at the lock too.
        const map = item(main, "mapArea")
        mouseDrag(map, 300, 300, 120, 0)
        mouseWheel(map, 300, 300, 0, 120)
        compare(main.chartMap.gestures, 0, "no pan while locked")
        compare(main.chartMap.moves, 0)
        compare(main.chartMap.scales.length, 0)
        compare(chartStub.zooms.length, 0, "no zoom while locked")

        const holdTarget = H.byName(overlay, "lockHold")
        mousePress(holdTarget)
        fixture.advance(1000)
        verify(fixture.touchLock.holdProgress > 0.6 && fixture.touchLock.holdProgress < 0.7, "ring at " + fixture.touchLock.holdProgress)
        mouseRelease(holdTarget)
        compare(fixture.touchLock.holdProgress, 0)
        verify(fixture.touchLock.locked, "a short press does not unlock")

        mousePress(holdTarget)
        fixture.advance(1500)
        mouseRelease(holdTarget)
        verify(!fixture.touchLock.locked, "1.5 s unlocks")
        verify(!overlay.visible)
        mouseWheel(map, 300, 300, 0, 120)
        compare(chartStub.zooms.length, 1, "the wheel zooms once unlocked")
        mouseDrag(map, 300, 300, 120, 0)
        compare(main.chartMap.gestures, 1, "the drag pans once unlocked")
        mouseClick(item(main, "tab-home"))
        compare(main.page, "home")
    }

    // A finger tap at the item's centre: the touch path, as on the panel (not the mouse path).
    function touchTap(it) {
        verify(it, "nothing to tap")
        touchEvent(it).press(0, it, it.width / 2, it.height / 2).commit()
        touchEvent(it).release(0, it, it.width / 2, it.height / 2).commit()
    }
    function pinchOut(it) {
        const cx = it.width / 2, cy = it.height / 2
        touchEvent(it).press(0, it, cx - 50, cy).press(1, it, cx + 50, cy).commit()
        for (let i = 1; i <= 10; ++i)
            touchEvent(it).move(0, it, cx - 50 - 10 * i, cy).move(1, it, cx + 50 + 10 * i, cy).commit()
        touchEvent(it).release(0, it, cx - 150, cy).release(1, it, cx + 150, cy).commit()
    }

    // The same through touch: taps on the tabs and palette, a pinch and a wheel turn on the chart
    // all stop at the lock; a finger hold on the padlock unlocks, and then they all work.
    function test_lockSwallowsTouchPinchAndWheel() {
        const main = makeMain(1024, 600)
        const map = item(main, "mapArea")
        waitForRendering(main.contentItem)
        touchTap(item(main, "lockButton"))
        verify(fixture.touchLock.locked, "a tap on Lock locks")
        touchTap(item(main, "tab-home"))
        compare(main.page, "view")
        touchTap(item(main, "paletteButton"))
        compare(fixture.settings.paletteMode, "auto")
        pinchOut(map)
        compare(chartStub.zooms.length, 0, "no pinch zoom while locked")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(chartStub.zooms.length, 0, "no wheel zoom while locked")
        touchEvent(map).press(0, map, 300, 300).commit()
        for (let i = 1; i <= 10; ++i)
            touchEvent(map).move(0, map, 300 + 12 * i, 300).commit()
        touchEvent(map).release(0, map, 420, 300).commit()
        compare(main.chartMap.gestures, 0, "no pan while locked: follow stays on")
        compare(main.chartMap.moves, 0)
        compare(main.chartMap.scales.length, 0)

        const holdTarget = item(main, "lockHold")
        touchEvent(holdTarget).press(0, holdTarget, holdTarget.width / 2, holdTarget.height / 2).commit()
        fixture.advance(1500)
        touchEvent(holdTarget).release(0, holdTarget, holdTarget.width / 2, holdTarget.height / 2).commit()
        verify(!fixture.touchLock.locked, "a 1.5 s finger hold unlocks")

        touchTap(item(main, "paletteButton"))
        compare(fixture.settings.paletteMode, "day")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(chartStub.zooms.length, 1, "the wheel zooms once unlocked")
        pinchOut(map)
        verify(chartStub.zooms.length > 1, "the pinch zooms once unlocked")
        touchTap(item(main, "tab-home"))
        compare(main.page, "home")
        touchTap(item(main, "tab-view-shipped-fish"))
        compare(main.page, "view")
        compare(fixture.views.currentId, "shipped-fish")
    }

    // The overlay is invisible while unlocked: it must not hold the key focus or eat keys then.
    function test_lockOverlayTakesNoKeysWhileUnlocked() {
        const main = makeMain(1024, 600)
        const overlay = item(main, "lockOverlay")
        waitForRendering(main.contentItem)
        keyClick(Qt.Key_B)
        compare(overlay.swallowed, 0, "a key before any lock")
        verify(!overlay.activeFocus, "no key focus before any lock")

        fixture.touchLock.lockNow()
        verify(overlay.activeFocus, "the overlay takes the key focus on lock")
        keyClick(Qt.Key_B)
        compare(overlay.swallowed, 1, "a key while locked")

        const holdTarget = item(main, "lockHold")
        mousePress(holdTarget)
        fixture.advance(1500)
        mouseRelease(holdTarget)
        verify(!fixture.touchLock.locked)
        const n = overlay.swallowed
        keyClick(Qt.Key_B)
        keyClick(Qt.Key_Tab)
        compare(overlay.swallowed, n, "keys after unlock")
        verify(!overlay.activeFocus, "no key focus after unlock")
    }

    // Every input the lock stops pulses the padlock (owner: the screen is locked, not dead): a tap,
    // a wheel turn, a pinch and a key press. The unlock hold does not count. A key reaches nothing.
    function test_lockPulsesOnEverySwallowedInputAndTakesKeys() {
        const main = makeMain(1024, 600)
        const map = item(main, "mapArea")
        const overlay = item(main, "lockOverlay")
        waitForRendering(main.contentItem)
        fixture.touchLock.lockNow()
        compare(overlay.swallowed, 0)
        verify(overlay.activeFocus, "the overlay holds the key focus while locked")
        verify(!overlay.pulsing)

        touchTap(map)
        compare(overlay.swallowed, 1, "a tap")
        verify(overlay.pulsing, "the tap pulses the padlock")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(overlay.swallowed, 2, "a wheel turn")
        const n = overlay.swallowed
        pinchOut(map)
        verify(overlay.swallowed > n, "a pinch")
        const k = overlay.swallowed
        keyClick(Qt.Key_Plus)
        keyClick(Qt.Key_Escape)
        compare(overlay.swallowed, k + 2, "key presses")
        compare(chartStub.zooms.length, 0, "nothing reached the chart")
        compare(main.chartMap.gestures, 0)
        compare(main.chartMap.scales.length, 0)
        compare(main.page, "view")
        verify(overlay.activeFocus, "still focused after the inputs")

        const holdTarget = item(main, "lockHold")
        const before = overlay.swallowed
        mousePress(holdTarget)
        fixture.advance(1500)
        mouseRelease(holdTarget)
        verify(!fixture.touchLock.locked, "the hold still unlocks")
        compare(overlay.swallowed, before, "the hold is not a swallowed input")
        tryVerify(() => !overlay.pulsing, 1000, "the pulse ends")
        mouseWheel(map, map.width / 2, map.height / 2, 0, 120)
        compare(chartStub.zooms.length, 1, "the wheel zooms once unlocked")
    }

    function test_lockHoldTargetIsOverTheLockButton() {
        const main = makeMain(1024, 600)
        fixture.touchLock.lockNow()
        const holdTarget = item(main, "lockHold")
        const button = item(main, "lockButton")
        tryVerify(() => {
            const a = holdTarget.mapToItem(main.contentItem, 0, 0), b = button.mapToItem(main.contentItem, 0, 0)
            return Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1
        }, 1000, "hold over the button")
        verify(holdTarget.width >= Units.mm(12) - 0.5 && holdTarget.height >= Units.mm(12) - 0.5)
    }

    // The bar on the view's right edge, or slid off it.
    function barShown(main) {
        const bar = item(main, "tabBar")
        return Math.abs(bar.x - (main.width - bar.width)) < 0.5
    }
    function barHidden(main) { return item(main, "tabBar").x >= main.width - 1 }
    // Shows the view `id` from its tab, then waits for the bar to slide off (hideDelayMs is short).
    function hideBarOn(main, id) {
        mouseClick(item(main, "tab-view-" + id))
        compare(main.page, "view")
        tryVerify(() => barHidden(main), 1000, "the bar slid off")
        verify(!item(main, "tabBar").shown)
    }

    function test_barHidesAfterDelayAndPlainTapShowsIt() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        main.hideDelayMs = 200
        mouseClick(item(main, "tab-view-shipped-nav"))
        verify(barShown(main))
        tryVerify(() => barHidden(main), 1000, "hidden after the delay and the slide: x " + bar.x)
        main.hideDelayMs = 2000 // long enough to see it back
        const map = item(main, "mapArea")
        mouseClick(map, map.width / 2, map.height / 2)
        verify(bar.shown)
        tryVerify(() => barShown(main), 1500, "back after the 150 ms slide")

        main.hideDelayMs = 200
        hideBarOn(main, "shipped-big")
        main.hideDelayMs = 2000
        const cells = item(main, "cellPage")
        verify(cells.visible)
        mouseClick(item(main, "cell-0"))
        verify(bar.shown, "a cell tap shows the bar")
        tryVerify(() => barShown(main), 1500)
        main.hideDelayMs = 200
        hideBarOn(main, "shipped-big")
        mouseClick(cells, 1, 1) // the gap round the cells
        verify(bar.shown, "a background tap shows the bar")
        tryVerify(() => barShown(main), 1500)
    }

    // The view's own buttons do their job and leave the bar hidden.
    function test_establishedButtonsLeaveTheBarHidden() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        main.hideDelayMs = 200
        hideBarOn(main, "shipped-nav")
        const stillHidden = what => {
            verify(!bar.shown, what + " leaves the bar hidden")
            verify(barHidden(main), what)
        }
        verify(!item(main, "zoomInButton").visible, "+ hides with the bar")
        verify(!item(main, "legendButton").visible, "Legend hides with the bar")
        chartStub.follow = false
        const recenter = item(main, "recenterButton")
        waitForRendering(recenter)
        mouseClick(recenter)
        verify(chartStub.follow, "recentered")
        stillHidden("Recenter")
        chartStub.target = { mmsi: 1 }
        const map = item(main, "mapArea")
        mouseClick(map, map.width / 2, map.height / 2)
        stillHidden("an AIS target")

        chartStub.target = undefined
        chartStub.fishAvailable = false
        fixture.views.currentId = "shipped-fish" // the tab is off screen with the bar
        stillHidden("the view switch")
        const chip = item(main, "noFishChip")
        verify(chip.visible)
        const plain = createTemporaryObject(spyComp, testCase, { target: item(main, "chartPage"), signalName: "plainTap" })
        mouseClick(chip)
        compare(plain.count, 0, "the chip takes its own tap")
        stillHidden("the No fishing chart chip")
    }

    // The hide slides the slots to the right edge with the bar (TR, BR, Right, Top and Bottom
    // follow it; TL, BL, Recenter and the chip stay put) and hides +, - and Legend; drawn sizes do
    // not change. The bar's return puts everything back.
    function test_slotsFollowTheBarAndTheButtonsHide() {
        chartStub.fishAvailable = false
        chartStub.follow = false
        const main = makeMain(1024, 600)
        main.hideDelayMs = 0 // never, until the boxes are recorded
        mouseClick(item(main, "tab-view-shipped-fish"))
        compare(main.page, "view")
        for (const [id, field, mm] of [["BL", "cog", 8], ["BR", "stw", 8], ["Top", "time", 6], ["Bottom", "pos", 5], ["Right", "hdg", 8]])
            fixture.draft.setSlot(id, true, field, mm)
        const page = item(main, "chartPage")
        const map = item(main, "mapArea")
        waitForRendering(page)
        const slots = H.findAll(page, it => it.slotId !== undefined && it.drawnMm !== undefined && it.visible)
        const slot = id => slots.find(s => s.slotId === id)
        for (const id of ["TL", "TR", "BL", "BR", "Top", "Bottom", "Right"]) verify(slot(id), id + " shown")
        const fixed = ["recenterButton", "noFishChip"].map(n => item(main, n))
        const hidden = ["zoomInButton", "zoomOutButton", "legendButton"].map(n => item(main, n))
        for (const it of fixed.concat(hidden)) verify(it.visible, it.objectName)
        const boxOf = it => H.box(it, main.contentItem)
        const watched = slots.concat(fixed, hidden)
        const before = watched.map(boxOf)
        const drawn = slots.map(s => s.drawnMm)
        const mapWidth = map.width
        const margin = Units.mm(1.5)

        main.hideDelayMs = 200
        // barHidden() is true a fraction of a pixel before the slide ends; the widths below are exact.
        tryVerify(() => item(main, "tabBar").x >= main.width - 0.01, 1500, "the bar slid all the way off")
        const right = boxOf(slot("Right"))
        fuzzyCompare(right.x + right.w, main.width, 1)
        for (const id of ["TR", "BR"]) {
            const b = boxOf(slot(id))
            fuzzyCompare(b.x + b.w, right.x - margin, 1, id + " at the edge, clear of the Right bar")
        }
        for (const id of ["Top", "Bottom"]) compare(boxOf(slot(id)).w, main.width, id)
        for (const it of [slot("TL"), slot("BL")].concat(fixed))
            compare(boxOf(it), before[watched.indexOf(it)], it.objectName || it.slotId)
        for (const it of hidden) verify(!it.visible, it.objectName + " hidden with the bar")
        compare(map.width, mapWidth, "the map keeps its width")
        fuzzyCompare(boxOf(map).x + map.width, right.x, 1, "the map runs up to the Right bar, at the edge")
        compare(slots.map(s => s.drawnMm), drawn, "drawn sizes unchanged")

        main.hideDelayMs = 2000 // long enough to see it back
        mouseClick(map, map.width / 2, map.height / 2)
        verify(item(main, "tabBar").shown)
        tryVerify(() => barShown(main) && JSON.stringify(watched.map(boxOf)) === JSON.stringify(before), 1500,
                  "every box back: " + JSON.stringify(watched.map(boxOf)))
        for (const it of hidden) verify(it.visible, it.objectName + " back with the bar")
        compare(slots.map(s => s.drawnMm), drawn)
        compare(map.width, mapWidth, "the map keeps its width with the bar back")

        // With no Right bar the map runs under the strip, shown or hidden.
        fixture.draft.setSlot("Right", false, "hdg", 8)
        compare(map.width, main.width)
        main.hideDelayMs = 200
        tryVerify(() => barHidden(main), 1500, "the bar slid off again")
        compare(map.width, main.width)
    }

    // A None view's cells widen into the strip when the bar slides off and come back exactly when it
    // shows; heights never change, digits never get smaller (they may refit larger, issue #35).
    function test_cellsFollowTheBar_data() { return H.sizes() }
    function test_cellsFollowTheBar(data) {
        fixture.settings.panelDiagonalIn = data.diagIn
        const main = makeMain(data.w, data.h)
        main.hideDelayMs = 0
        mouseClick(item(main, "tab-view-shipped-big"))
        compare(main.page, "view")
        const page = item(main, "cellPage")
        waitForRendering(page)
        const cells = H.findAll(page, it => it.objectName.startsWith("cell-") && it.visible)
                          .sort((a, b) => a.objectName.localeCompare(b.objectName))
        compare(cells.length, 2)
        const boxOf = it => H.box(it, main.contentItem)
        const before = cells.map(boxOf)
        const digits = () => cells.map(c => H.byName(c, "cellValue").fontInfo.pixelSize)
        const digitsBefore = digits()
        const gap = page.gap

        main.hideDelayMs = 200
        tryVerify(() => item(main, "tabBar").x >= main.width - 0.01, 1500, "the bar slid all the way off")
        const after = cells.map(boxOf)
        for (let i = 0; i < cells.length; ++i) {
            compare(after[i].y, before[i].y, "cell-" + i + " y")
            compare(after[i].h, before[i].h, "cell-" + i + " height")
            fuzzyCompare(after[i].w, (main.width - 3 * gap) / 2, 1, "cell-" + i + " half of the full width")
        }
        compare(after[0].x, before[0].x, "cell-0 stays at the left edge")
        fuzzyCompare(after[1].x + after[1].w, main.width - gap, 1, "cell-1 reaches the right edge")
        const digitsAfter = digits()
        for (let i = 0; i < cells.length; ++i) verify(digitsAfter[i] >= digitsBefore[i] - 0.01, "digits never smaller: " + digitsBefore + " to " + digitsAfter)

        main.hideDelayMs = 2000
        mouseClick(cells[0], cells[0].width / 2, cells[0].height / 2) // a plain tap brings the bar back
        verify(item(main, "tabBar").shown)
        tryVerify(() => barShown(main) && JSON.stringify(cells.map(boxOf)) === JSON.stringify(before), 1500,
                  "every cell back: " + JSON.stringify(cells.map(boxOf)))
        compare(digits(), digitsBefore, "digits back to their size")
    }

    // The legend sheet follows the bar: once it slides off, the sheet covers the strip too, so
    // none of the slots that moved into it shows beside the sheet.
    function test_legendSheetCoversTheStripWhenTheBarHides() {
        const main = makeMain(1024, 600)
        main.hideDelayMs = 0
        mouseClick(item(main, "tab-view-shipped-nav"))
        const page = item(main, "chartPage")
        const sheet = item(main, "legendSheet")
        mouseClick(item(main, "legendButton"))
        verify(sheet.visible)
        main.hideDelayMs = 200
        tryVerify(() => barHidden(main), 1500, "the bar slid off")
        tryVerify(() => Math.abs(H.box(sheet, page).x + sheet.width - page.width) < 1, 1500,
                  "the sheet runs to the page's edge: " + JSON.stringify(H.box(sheet, page)))
    }

    function test_barNeverHidesOnHomeTracksSettingsAbout() {
        const main = makeMain(1024, 600)
        main.hideDelayMs = 100
        for (const p of ["home", "tracks", "settings", "about"]) {
            main.page = p
            wait(300)
            verify(item(main, "tabBar").shown, p)
            verify(barShown(main), p)
        }
    }

    function test_offNeverHides() {
        fixture.settings.tabBarHideS = 0
        const main = makeMain(1024, 600)
        compare(main.hideDelayMs, 0)
        mouseClick(item(main, "tab-view-shipped-nav"))
        wait(300)
        verify(item(main, "tabBar").shown)
        verify(barShown(main))
    }

    // A bar button press starts the delay again; so does a tap on the bar between its buttons.
    function test_barTapRestartsTheDelay() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        // Each check is past the deadline before it (so only a restart keeps the bar) and 800 ms
        // before its own (so a slow wait cannot fail it).
        main.hideDelayMs = 2000
        mouseClick(item(main, "tab-view-shipped-nav"))
        wait(1200)
        mouseClick(item(main, "paletteButton"))
        wait(1200)
        verify(bar.shown, "2400 ms after the tab tap, 1200 ms after the palette")
        mouseClick(bar, bar.width / 2, bar.height - Units.mm(0.5)) // the bottom margin, under the buttons
        wait(1200)
        verify(bar.shown, "2400 ms after the palette, 1200 ms after a tap between the buttons")
        tryVerify(() => barHidden(main), 5000, "then it hides")
    }

    // A tap on the strip while the bar slides shows it, and presses nothing under the finger.
    function test_tapDuringTheSlideShows() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        const home = item(main, "tab-home")
        const p = home.mapToItem(main.contentItem, home.width / 2, home.height / 2)
        bar.shown = false // the slide starts
        mouseClick(main.contentItem, p.x, p.y)
        verify(bar.shown)
        compare(main.page, "view", "the house tab under the finger was not pressed")
        tryVerify(() => barShown(main), 1500)
    }

    function test_lockShowsTheBarFirst() {
        const main = makeMain(1024, 600)
        const bar = item(main, "tabBar")
        main.hideDelayMs = 200
        hideBarOn(main, "shipped-nav")
        fixture.touchLock.lockNow()
        verify(bar.shown, "locking shows the bar")
        const holdTarget = item(main, "lockHold")
        const button = item(main, "lockButton")
        tryVerify(() => {
            const a = holdTarget.mapToItem(main.contentItem, 0, 0), b = button.mapToItem(main.contentItem, 0, 0)
            return barShown(main) && Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1
        }, 1000, "hold over the shown Lock button")
        wait(400)
        verify(barShown(main), "the bar stays while locked")
    }

    function test_tabBarRecordIndicatorFollowsTheSetting() {
        const main = makeMain(1024, 600)
        const ind = item(main, "recordIndicator")
        verify(!ind.visible)
        fixture.settings.trackRecording = true
        verify(ind.visible)
        const tab = item(main, "tab-home")
        verify(ind.width < Units.mm(4) && ind.height < Units.mm(4))
        const a = ind.mapToItem(main.contentItem, 0, 0), t = tab.mapToItem(main.contentItem, 0, 0)
        verify(a.x >= t.x && a.x + ind.width <= t.x + tab.width && a.y >= t.y && a.y + ind.height <= t.y + tab.height,
               "indicator sits inside the house tab: it adds no height to the tab column")
    }

    // The house tab draws an Icon: Qt Svg loads in the test process (no image format warning).
    function test_houseTabIconLoads() {
        const main = makeMain(1024, 600)
        const icons = H.findAll(item(main, "tab-home"), it => it.sourceSize !== undefined && it.name === "home")
        compare(icons.length, 1)
        tryCompare(icons[0], "status", Image.Ready)
        verify(icons[0].width >= Units.mm(6), "a visible icon")
        waitForRendering(main.contentItem)
    }

    function test_splashShowsTheLogo_data() {
        return [
            { tag: "1024x600", w: 1024, h: 600 },
            { tag: "1280x800", w: 1280, h: 800 }
        ]
    }
    // The logo fills the splash (cropped, never stretched); the info lines sit along the bottom in
    // the space left and right of the emblem (version and packs left, the notice right), white by day
    // and dusk, the night red at night.
    function test_splashShowsTheLogo(data) {
        const splash = createTemporaryObject(splashComp, testCase, { width: data.w, height: data.h, appInfo: fixture.appInfo })
        verify(splash, "splash")
        compare(splash.minimumMs, 5000)
        const logo = H.byName(splash, "splashLogo")
        verify(logo, "splashLogo")
        tryCompare(logo, "status", Image.Ready)
        waitForRendering(splash)
        compare(H.box(logo, splash), { x: 0, y: 0, w: splash.width, h: splash.height })
        compare(logo.fillMode, Image.PreserveAspectCrop)
        compare(logo.sourceSize.width, 1408)
        compare(logo.sourceSize.height, 768)
        const version = H.findAll(splash, it => it.text !== undefined && it.text.startsWith("Plotter "))
        compare(version.length, 1)
        // The emblem spans the middle half of the image; the crop takes the same off each side.
        const drawnW = 1408 * Math.max(splash.width / 1408, splash.height / 768)
        fuzzyCompare(splash.emblemLeft, 0.25 * drawnW - (drawnW - splash.width) / 2, 0.5)
        fuzzyCompare(splash.emblemRight, splash.width - splash.emblemLeft, 0.5)
        verify(splash.emblemLeft > Units.mm(30), "a band left of the emblem: " + splash.emblemLeft)
        const left = [version[0]].concat(["splashCharts", "splashBathy"].map(n => H.byName(splash, n)))
        const notice = H.byName(splash, "splashNotice")
        const lines = left.concat([notice])
        let prevTop = -1
        for (const l of lines) {
            verify(l && l.visible, l ? l.text : "line")
            const b = H.box(l, splash)
            verify(b.y >= 0 && b.y + b.h <= splash.height, l.text + " inside the splash")
            if (l === notice) verify(b.x >= splash.emblemRight && b.x + b.w <= splash.width, "notice right of the emblem: " + JSON.stringify(b))
            else verify(b.x >= 0 && b.x + b.w <= splash.emblemLeft, l.text + " left of the emblem: " + JSON.stringify(b))
            verify(l.paintedWidth <= l.width + 0.5, l.text + " wraps inside its band")
            compare(l.style, Text.Outline, l.text + " outlined, so it reads over the logo")
            verify(b.y >= splash.height * 0.6, l.text + " along the bottom: top " + b.y)
            if (l !== notice) {
                verify(b.y > prevTop, l.text + " below the line before it")
                prevTop = b.y
            }
        }
        for (const p of ["day", "dusk", "night"]) {
            Theme.palette = p
            const want = p === "night" ? Theme.text : "#ffffff"
            verify(Qt.colorEqual(splash.infoColor, want), p + ": " + splash.infoColor)
            for (const l of lines) verify(Qt.colorEqual(l.color, want), p + ": " + l.text)
            compare(logo.opacity, p === "night" ? 0.3 : 1)
        }
    }

    // The chart notice setting: off, the notice line goes from the chart (the Bottom bar and the
    // corner area take its room) and from the boot splash; on again, it is back.
    function test_chartNoticeFollowsTheSetting() {
        const main = makeMain(1024, 600)
        mouseClick(item(main, "tab-view-shipped-nav"))
        fixture.draft.setSlot("Bottom", true, "pos", 5)
        const page = item(main, "chartPage")
        const bar = item(main, "noticeBar")
        const area = item(main, "cornerArea")
        const splash = item(main, "splash")
        waitForRendering(page)
        verify(bar.visible && bar.height > 0)
        verify(splash.noticeShown)
        fixture.settings.showChartNotice = false
        verify(!bar.visible, "the notice bar hides")
        compare(bar.height, 0)
        const bottom = H.byName(page, "slot-Bottom")
        verify(bottom.visible)
        fuzzyCompare(bottom.y + bottom.height, page.height, 0.5, "Bottom on the page's bottom edge")
        fixture.draft.setSlot("Bottom", false, "pos", 5)
        fuzzyCompare(area.y + area.height, page.height - Units.mm(1.5), 0.5, "the corner area down to the bottom margin")
        verify(!splash.noticeShown, "the splash leaves the notice out too")
        fixture.settings.showChartNotice = true
        verify(bar.visible && bar.height > 0)
        verify(splash.noticeShown)
    }

    function test_splashNoticeFollowsNoticeShown() {
        const off = createTemporaryObject(splashComp, testCase, { width: 1024, height: 600, appInfo: fixture.appInfo, noticeShown: false })
        const notice = H.byName(off, "splashNotice")
        compare(notice.text, "") // the pack's own notice is hidden by the setting
        verify(!notice.visible)
        off.noticeShown = true
        verify(notice.text !== "", "the pack has a notice")
        verify(notice.visible)
    }
}
