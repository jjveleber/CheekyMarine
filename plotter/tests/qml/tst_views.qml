import QtQuick
import QtTest
import CheekyMarine
import "Helpers.js" as H

// The app shell over the saved views: the favourite tabs and the house tab, the Home page of
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
        property var aisSelection: ({})
        property var zooms: [] // zoomBy calls: log2 deltas
        function targetAt(p, r) { return undefined }
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
    // A 0.7 s mouse hold on `it` (the hold is 0.6 s).
    function hold(it) {
        verify(it, "nothing to hold")
        mousePress(it)
        wait(700)
        mouseRelease(it)
    }
    // The tile menu open for the view `id`.
    function menuFor(main, id) {
        const menu = item(main, "tileMenu")
        if (!(menu.visible && menu.viewId === id)) {
            if (menu.visible) mouseClick(H.byName(menu, "menu-close"))
            hold(item(main, "tile-" + id))
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

    // Five favourites fit at both sizes on the 10.1 in panel; a sixth is a plain view whose tile
    // says so.
    function test_favouriteTabsFollowCapacity_data() { return H.sizes() }
    function test_favouriteTabsFollowCapacity(data) {
        const main = makeMain(data.w, data.h)
        compare(fixture.views.favouriteCapacity, 5)
        for (let i = 0; i < 2; ++i) fixture.views.setFavourite(fixture.views.add(), true)
        compare(viewTabs(main).length, 5)
        const sixth = fixture.views.add()
        fixture.views.setFavourite(sixth, true)
        compare(viewTabs(main).length, 5)
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

    // A small panel diagonal leaves the column fewer favourite tabs; every tab and control stays
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
        const capacity = PanelMath.favouriteCapacity(bar.height / Units.pxPerMm)
        compare(fixture.views.favouriteCapacity, capacity)
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
        hold(item(main, "tab-view-shipped-fish"))
        compare(held.count, 1)
        compare(held.signalArguments[0][0], "shipped-fish")
        compare(selected.count, 0)
        compare(fixture.views.currentId, "shipped-nav")
        mouseClick(item(main, "tab-home"))
        mouseClick(item(main, "paletteButton"))
        compare(touched.count, 3, "every bar button press")
    }
    Component { id: spyComp; SignalSpy {} }

    function test_nonFavouriteViewHighlightsHouse() {
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
        const margin = Units.mm(3)
        const cols = (home.width - home.rightInset - 2 * margin) / 3 >= Units.mm(40) ? 3 : 2
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
        verify(stars.every(s => s && s.visible && s.name === "star"), "the shipped views are favourites")
        compare(H.findAll(item(main, "tile-tracks"), it => it.name === "map").length, 1)
        compare(H.findAll(item(main, "tile-settings"), it => it.name === "settings").length, 1)
        compare(item(main, "tile-new").text, "+ New view")
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
        const fav = H.byName(menu, "menu-favourite")
        compare(fav.text, "Favourite off")
        mouseClick(fav)
        verify(!fixture.views.viewJson("shipped-fish").favourite)
        verify(!H.byName(item(main, "tile-shipped-fish"), "tileStar").visible, "star gone")
        compare(H.byName(main.contentItem, "tab-view-shipped-fish"), null)
        menu = menuFor(main, "shipped-fish")
        compare(H.byName(menu, "menu-favourite").text, "Favourite on")

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

    // Every page keeps its controls left of the bar.
    function test_pagesHonourRightInset_data() {
        let out = []
        for (const s of H.sizes())
            for (const p of [["tracks", "tracksPage"], ["settings", "settingsPage"], ["about", "aboutPage"], ["home", "homePage"]])
                out.push({ tag: s.tag + " " + p[0], w: s.w, h: s.h, page: p[0], item: p[1] })
        return out
    }
    function test_pagesHonourRightInset(data) {
        fixture.addTrack(1.7e9)
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

    // The splash draws an Icon: Qt Svg loads in the test process (no image format warning).
    function test_splashShowsAnIcon() {
        const splash = createTemporaryObject(splashComp, testCase, { width: 1024, height: 600, appInfo: fixture.appInfo })
        const icons = H.findAll(splash, it => it.sourceSize !== undefined && it.name !== undefined && it.name !== "")
        compare(icons.length, 1)
        tryCompare(icons[0], "status", Image.Ready)
        verify(icons[0].width >= Units.mm(10), "a visible icon")
        waitForRendering(splash)
    }
}
