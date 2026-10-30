import QtQuick
import QtTest
import CheekyMarine

// Pages construct without warnings at both panel sizes, every BigButton is at least 12 mm both
// ways, the no-data banner text, slot digit size, slot editing and the numbers page cells.
TestCase {
    id: testCase
    name: "Pages"
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
        property var legend: [{ abbr: "Blds", meaning: "boulders", kind: "type" },
                              { abbr: "Cb", meaning: "cobbles", kind: "type" },
                              { abbr: "Sh", meaning: "shells", kind: "type" }]
        property var aisSelection: ({})
        property var selected: []
        function selectAt(p, r) { selected.push(r) }
        function clearTarget() { aisSelection = ({}) }
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
            function moveBy(p) {}
            function scaleBy(f, p) {}
        }
    }
    Component { id: mainComp; Main {} }
    Component { id: chartPageComp; ChartPage {} }
    Component { id: numbersPageComp; NumbersPage {} }
    Component { id: aboutPageComp; AboutPage {} }
    Component { id: recoveryComp; RecoveryScreen {} }
    Component { id: bannerComp; NoDataBanner {} }
    Component { id: slotComp; SlotView {} }
    Component { id: settingsComp; SettingsPage {} }
    Component { id: tracksComp; TracksPage {} }

    function sizes() {
        return [{ tag: "1024x600", w: 1024, h: 600, ppm: 4.626 }, { tag: "1280x800", w: 1280, h: 800, ppm: 5.884 }]
    }

    function init() {
        failOnWarning(/.*/)
        fixture.reset()
        Units.windowWidth = 1280
        Units.windowHeight = 800
        Units.diagonalIn = 10.1
    }

    // Every item under `root` (depth first) for which pred holds.
    function findAll(root, pred) {
        let out = []
        const stack = [root]
        while (stack.length > 0) {
            const it = stack.pop()
            if (pred(it)) out.push(it)
            for (let i = 0; i < it.children.length; ++i) stack.push(it.children[i])
        }
        return out
    }
    function byName(root, name) {
        const l = findAll(root, it => it.objectName === name)
        return l.length > 0 ? l[0] : null
    }

    function checkBigButtons(root) {
        const buttons = findAll(root, it => it.isBigButton === true)
        verify(buttons.length > 0, "no BigButton found")
        const min = Units.mm(12) - 0.5
        for (const b of buttons) {
            verify(b.width >= min && b.height >= min,
                   "BigButton '" + b.text + "' (" + b.objectName + ") is " + b.width + "x" + b.height + ", min " + min)
        }
        return buttons.length
    }

    function makeMain(w, h) {
        const main = createTemporaryObject(mainComp, testCase, {
            width: w, height: h,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), paletteController: paletteStub,
            settings: fixture.settings, vessel: fixture.vessel, appInfo: fixture.appInfo,
            slotsModel: fixture.slotsModel, numbersModel: fixture.numbersModel,
            touchLock: fixture.touchLock, tracksController: fixture.tracksController
        })
        verify(main, "Main")
        tryCompare(main, "width", w)
        return main
    }

    function test_mainConstructs_data() { return sizes() }
    function test_mainConstructs(data) {
        const main = makeMain(data.w, data.h)
        compare(Units.windowWidth, data.w)
        compare(Units.windowHeight, data.h)
        fuzzyCompare(Units.pxPerMm, data.ppm, 0.001)
        // All pages exist in the stack, so the walk covers them.
        for (const n of ["chartPage", "numbersPage", "tracksPage", "settingsPage", "aboutPage", "tabBar", "splash"])
            verify(byName(main.contentItem, n), n)
        checkBigButtons(main.contentItem)
    }

    function test_tabsAre15mm() {
        const main = makeMain(1024, 600)
        const tabs = findAll(main.contentItem, it => it.isBigButton === true && it.objectName.startsWith("tab-"))
        compare(tabs.length, 4)
        for (const t of tabs) verify(t.width >= Units.mm(15) - 0.5 && t.height >= Units.mm(15) - 0.5, t.objectName)
        const bar = byName(main.contentItem, "tabBar")
        tryVerify(() => Math.abs(bar.mapToItem(main.contentItem, 0, 0).x + bar.width - main.width) < 0.5,
                  1000, "tab bar on the right edge")
    }

    function test_tabsSwitchPagesAndPaletteCycles() {
        const main = makeMain(1024, 600)
        byName(main.contentItem, "splash").visible = false
        mouseClick(byName(main.contentItem, "tab-numbers"))
        compare(main.page, "numbers")
        verify(byName(main.contentItem, "numbersPage").visible)
        compare(fixture.settings.paletteMode, "auto")
        const pal = byName(main.contentItem, "paletteButton")
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "day")
        mouseClick(pal)
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "night")
        mouseClick(pal)
        compare(fixture.settings.paletteMode, "auto")
    }

    function test_editOverlaysFromSettings() {
        const main = makeMain(1024, 600)
        byName(main.contentItem, "splash").visible = false
        mouseClick(byName(main.contentItem, "tab-settings"))
        waitForRendering(byName(main.contentItem, "settingsPage"))
        tap(byName(main.contentItem, "editOverlaysButton"))
        compare(main.page, "chart")
        const chart = byName(main.contentItem, "chartPage")
        verify(chart.editing)
        mouseClick(byName(chart, "editDoneButton"))
        verify(!chart.editing)
    }

    function test_pagesConstruct_data() { return sizes() }
    function test_pagesConstruct(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const props = { width: data.w - Units.mm(17), height: data.h }
        const chart = createTemporaryObject(chartPageComp, testCase, Object.assign({
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), slotsModel: fixture.slotsModel }, props))
        verify(chart, "ChartPage")
        checkBigButtons(chart)
        const numbers = createTemporaryObject(numbersPageComp, testCase, Object.assign({ model: fixture.numbersModel }, props))
        verify(numbers, "NumbersPage")
        checkBigButtons(numbers)
        const about = createTemporaryObject(aboutPageComp, testCase, Object.assign({ appInfo: fixture.appInfo }, props))
        verify(about, "AboutPage")
        checkBigButtons(about)
        const rec = createTemporaryObject(recoveryComp, testCase, { width: data.w, height: data.h, recovery: fixture.recovery })
        verify(rec, "RecoveryScreen")
        compare(checkBigButtons(rec), 2) // Start fresh, and Try again for an Io error
    }

    function test_aisSheet() {
        Units.windowWidth = 1280
        Units.windowHeight = 800
        const chart = createTemporaryObject(chartPageComp, testCase, {
            width: 1280 - Units.mm(17), height: 800,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), slotsModel: fixture.slotsModel })
        const sheet = byName(chart, "aisSheet")
        verify(sheet, "aisSheet")
        verify(!sheet.visible)
        chartStub.aisSelection = { mmsi: "367000001", name: "SEA QUEEN", cls: "A", sog: "10.0", cog: "090",
                                   range: "1.0", bearing: "307", posAge: "12 s" }
        verify(sheet.visible)
        const values = findAll(sheet, it => it.objectName === "aisValue").map(it => it.text)
        verify(values.indexOf("SEA QUEEN") >= 0, "name")
        verify(values.indexOf("367000001") >= 0, "mmsi")
        compare(values.length, 8)
        compare(checkBigButtons(sheet), 1) // the Close button only
        const close = byName(sheet, "aisCloseButton")
        verify(close)
        close.clicked()
        verify(!sheet.visible)
    }

    function test_legendSheet() {
        Units.windowWidth = 1280
        Units.windowHeight = 800
        const chart = createTemporaryObject(chartPageComp, testCase, {
            width: 1280 - Units.mm(17), height: 800,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), slotsModel: fixture.slotsModel })
        const sheet = byName(chart, "legendSheet")
        verify(sheet, "legendSheet")
        verify(!sheet.visible)
        const open = byName(chart, "legendButton")
        verify(open && open.isBigButton)
        open.clicked()
        verify(sheet.visible)
        const rows = findAll(sheet, it => it.objectName === "legendRow")
        compare(rows.length, chartStub.legend.length)
        for (const r of rows)
            verify(r.height >= Units.mm(12), "row height")
        checkBigButtons(sheet)
        const close = byName(sheet, "legendCloseButton")
        verify(close)
        close.clicked()
        verify(!sheet.visible)
    }

    function test_allSlotsOnFitWithoutOverlap_data() { return sizes() }
    function test_allSlotsOnFitWithoutOverlap(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        for (const id of ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"]) {
            const m = fixture.slotsModel
            const i = ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"].indexOf(id)
            const field = ["depth", "sog", "cog", "wtemp", "time", "pos", "stw", "hdg"][i]
            const size = ["large", "large", "medium", "medium", "small", "small", "medium", "medium"][i]
            m.setSlot(id, true, field, size)
        }
        const chart = createTemporaryObject(chartPageComp, testCase, {
            width: data.w - Units.mm(17), height: data.h,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), slotsModel: fixture.slotsModel })
        const slots = findAll(chart, it => it.objectName.startsWith("slot-") && it.visible)
        compare(slots.length, 8)
        for (let a = 0; a < slots.length; ++a) {
            for (let b = a + 1; b < slots.length; ++b) {
                const p = slots[a].mapToItem(chart, 0, 0), q = slots[b].mapToItem(chart, 0, 0)
                const overlap = p.x < q.x + slots[b].width && q.x < p.x + slots[a].width
                             && p.y < q.y + slots[b].height && q.y < p.y + slots[a].height
                verify(!overlap, slots[a].objectName + " overlaps " + slots[b].objectName)
            }
        }
        // Bars shrink the viewport: the map area lies between them.
        const map = byName(chart, "mapArea")
        const top = byName(chart, "slot-Top"), left = byName(chart, "slot-Left")
        verify(map.y >= top.height - 0.5, "map below the top bar")
        verify(map.x >= left.width - 0.5, "map right of the left bar")
    }

    function test_noDataBanner() {
        const banner = createTemporaryObject(bannerComp, testCase, { width: 1000, live: false })
        verify(banner.visible)
        compare(banner.text, "No data from N2K")
        banner.schemaMismatch = true
        compare(banner.text, "Daemon too new or too old")
        banner.live = true
        verify(!banner.visible)
    }

    function test_mainBannerFollowsSchemaMismatch() {
        const main = makeMain(1024, 600)
        const banner = byName(main.contentItem, "noDataBanner")
        verify(banner.visible)
        compare(banner.text, "No data from N2K")
        fixture.appInfo.setSchemaMismatch(2)
        compare(banner.text, "Daemon too new or too old")
        fixture.setVessel(3, 2)
        verify(!banner.visible)
    }

    // A large slot's "8" is drawn at least 25 mm tall (95 %).
    function test_largeSlotDigitHeight() {
        Units.windowWidth = 1280
        Units.windowHeight = 800
        const slot = createTemporaryObject(slotComp, testCase, {
            x: 20, y: 20, slotId: "TL", on: true, field: "depth", fieldLabel: "Depth", size: "large",
            formatted: "8", unit: "ft" })
        const value = byName(slot, "slotValue")
        verify(value)
        waitForRendering(slot)
        const img = grabImage(value)
        // The text item's box reaches over the field label above it: the digit is the longest run
        // of rows with ink.
        const bg = img.pixel(0, 0)
        let rows = 0, run = 0
        for (let y = 0; y < img.height; ++y) {
            let ink = false
            for (let x = 0; x < img.width && !ink; ++x) {
                const c = img.pixel(x, y)
                ink = Math.abs(c.r - bg.r) + Math.abs(c.g - bg.g) + Math.abs(c.b - bg.b) > 0.3
            }
            run = ink ? run + 1 : 0
            rows = Math.max(rows, run)
        }
        verify(rows >= Units.mm(25) * 0.95, "8 is " + rows + " px tall, want " + Units.mm(25) * 0.95)
        verify(rows <= Units.mm(25) * 1.1, "8 is " + rows + " px tall, want about " + Units.mm(25))
    }

    function test_slotEditorChangesASlot() {
        const chart = createTemporaryObject(chartPageComp, testCase, {
            width: 1200, height: 800, chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase),
            slotsModel: fixture.slotsModel })
        const bl = byName(chart, "slot-BL")
        verify(!bl.visible) // off by default
        chart.editing = true
        verify(bl.visible)
        mouseClick(bl)
        const editor = byName(chart, "slotEditor")
        verify(editor.visible)
        mouseClick(byName(editor, "choice-on"))
        mouseClick(byName(editor, "choice-field-rpm"))
        mouseClick(byName(editor, "choice-size-large"))
        mouseClick(byName(editor, "editorDone"))
        verify(!editor.visible)
        chart.editing = false
        verify(bl.visible)
        compare(bl.field, "rpm")
        compare(bl.size, "large")
    }

    function test_numbersCellsAndPicker() {
        const page = createTemporaryObject(numbersPageComp, testCase, { width: 1200, height: 800, model: fixture.numbersModel })
        compare(findAll(page, it => it.objectName.startsWith("cell-") && it.visible).length, 2)
        fixture.setVessel(3 * 0.3048, 0)
        compare(byName(page, "cell-0").formatted, "3.0")
        mouseClick(byName(page, "cell-1"))
        const editor = byName(page, "slotEditor")
        verify(editor.visible)
        mouseClick(byName(editor, "choice-cells-4"))
        mouseClick(byName(editor, "choice-field-cog"))
        mouseClick(byName(editor, "editorDone"))
        compare(fixture.numbersModel.count, 4)
        compare(fixture.settings.bigNumbers, ["depth", "cog", "cog", "stw"])
        tryCompare(page, "cellCount", 4)
        compare(findAll(page, it => it.objectName.startsWith("cell-") && it.visible).length, 4)
    }

    function makeSettings() {
        const page = createTemporaryObject(settingsComp, testCase, { width: 1200, height: 800, settings: fixture.settings })
        verify(page, "SettingsPage")
        return page
    }
    // Scrolls every Flickable above `item` so the item is on screen, then clicks it.
    function tap(item) {
        verify(item, "nothing to tap")
        for (let a = item.parent; a; a = a.parent) {
            if (a.contentItem !== undefined && a.contentY !== undefined) {
                const p = item.mapToItem(a, 0, 0)
                if (p.y < 0 || p.y + item.height > a.height)
                    a.contentY = Math.max(0, Math.min(a.contentHeight - a.height, a.contentY + p.y - Units.mm(2)))
            }
        }
        mouseClick(item)
    }
    function pick(page, row, choice) {
        tap(byName(page, row))
        waitForRendering(byName(page, "settingsList")) // the list lays out on the next frame
        tap(byName(page, "choice-" + choice))
    }

    function test_settingsConstructs_data() { return sizes() }
    function test_settingsConstructs(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const page = createTemporaryObject(settingsComp, testCase, { width: data.w - Units.mm(17), height: data.h, settings: fixture.settings })
        verify(page, "SettingsPage")
        checkBigButtons(page)
        verify(byName(page, "editOverlaysButton"))
        verify(byName(page, "aboutButton"))
    }

    function test_settingsInvalidDepthShowsReasonAndIsNotSaved() {
        const page = makeSettings()
        const deep = fixture.settings.deepM
        verify(fixture.settings.setDepths(1.8288, deep - 0.3048, deep)) // safety is deep minus 1 ft
        const before = fixture.settings.safetyM
        verify(!byName(page, "depthError").visible)
        tap(byName(page, "safetyPlus"))
        compare(fixture.settings.safetyM, before)
        verify(byName(page, "depthError").visible)
        compare(byName(page, "depthError").text, "Safety must be less than deep.")
        tap(byName(page, "safetyMinus"))
        verify(fixture.settings.safetyM < before)
        verify(!byName(page, "depthError").visible)
    }

    function test_settingsDepthStepFollowsUnit() {
        const page = makeSettings()
        compare(byName(page, "shallowValue").text, "6 ft")
        tap(byName(page, "shallowPlus"))
        compare(byName(page, "shallowValue").text, "7 ft")
        fuzzyCompare(fixture.settings.shallowM, 7 * 0.3048, 1e-6)
        pick(page, "row-depthUnit", "m")
        compare(fixture.settings.depthUnit, "m")
        verify(byName(page, "safetyValue").text.endsWith(" m"), byName(page, "safetyValue").text)
        const m0 = fixture.settings.deepM
        tap(byName(page, "deepPlus"))
        fuzzyCompare(fixture.settings.deepM, m0 + 0.5, 1e-6)
        pick(page, "row-depthUnit", "fm")
        verify(byName(page, "safetyValue").text.endsWith(" fm"))
        const f0 = fixture.settings.deepM
        tap(byName(page, "deepMinus"))
        fuzzyCompare(fixture.settings.deepM, f0 - 0.9144, 1e-6)
    }

    function test_settingsDepthLimits() {
        const page = makeSettings()
        verify(fixture.settings.setDepths(0.5, 1.0, 60.0))
        tap(byName(page, "deepPlus"))
        compare(fixture.settings.deepM, 60.0)
        verify(byName(page, "depthError").visible)
        tap(byName(page, "shallowMinus"))
        compare(fixture.settings.shallowM, 0.5)
    }

    function test_settingsChoiceRows_data() {
        return [
            { row: "row-speedUnit", choice: "kmh", key: "speedUnit", want: "kmh" },
            { row: "row-tempUnit", choice: "C", key: "tempUnit", want: "C" },
            { row: "row-orientation", choice: "north", key: "orientation", want: "north" },
            { row: "row-orientation", choice: "course", key: "orientation", want: "course" },
            { row: "row-paletteMode", choice: "night", key: "paletteMode", want: "night" },
            { row: "row-touchLock", choice: "0", key: "touchLockTimeoutS", want: 0 },
            { row: "row-touchLock", choice: "30", key: "touchLockTimeoutS", want: 30 },
            { row: "row-touchLock", choice: "300", key: "touchLockTimeoutS", want: 300 },
            { row: "row-trackInterval", choice: "30", key: "trackIntervalS", want: 30 },
            { row: "row-trackDistance", choice: "25", key: "trackMinDistanceM", want: 25 }
        ]
    }
    function test_settingsChoiceRows(data) {
        const page = makeSettings()
        pick(page, data.row, data.choice)
        compare(fixture.settings[data.key], data.want)
        verify(!byName(page, "settingsList").visible)
    }

    function test_settingsOffsetToggleAndDiagonal() {
        const page = makeSettings()
        const on = fixture.settings.applyDepthOffset
        tap(byName(page, "row-applyOffset"))
        compare(fixture.settings.applyDepthOffset, !on)
        compare(byName(page, "diagonalValue").text, "10.1 in")
        tap(byName(page, "diagonalPlus"))
        compare(fixture.settings.panelDiagonalIn, 10.2)
        tap(byName(page, "diagonalMinus"))
        tap(byName(page, "diagonalMinus"))
        compare(fixture.settings.panelDiagonalIn, 10.0)
        fixture.settings.panelDiagonalIn = 7.0
        tap(byName(page, "diagonalMinus"))
        compare(fixture.settings.panelDiagonalIn, 7.0)
        fixture.settings.panelDiagonalIn = 15.0
        tap(byName(page, "diagonalPlus"))
        compare(fixture.settings.panelDiagonalIn, 15.0)
    }

    function test_settingsShowsChartDepthNote() {
        const page = makeSettings()
        verify(findAll(page, it => it.text === "Chart depths are in feet").length === 1)
    }

    function test_settingsTabInMain() {
        const main = makeMain(1024, 600)
        byName(main.contentItem, "splash").visible = false
        mouseClick(byName(main.contentItem, "tab-settings"))
        verify(byName(main.contentItem, "settingsPage").visible)
        waitForRendering(byName(main.contentItem, "settingsPage"))
        tap(byName(main.contentItem, "aboutButton"))
        compare(main.page, "about")
    }

    function test_lockSwallowsTouchesAndLongPressUnlocks() {
        const main = makeMain(1024, 600)
        byName(main.contentItem, "splash").visible = false
        const overlay = byName(main.contentItem, "lockOverlay")
        verify(!overlay.visible, "no overlay while unlocked")
        mouseClick(byName(main.contentItem, "lockButton"))
        verify(fixture.touchLock.locked, "the Lock button locks")
        verify(overlay.visible)
        mouseClick(byName(main.contentItem, "tab-numbers"))
        compare(main.page, "chart")
        mouseClick(byName(main.contentItem, "paletteButton"))
        compare(fixture.settings.paletteMode, "auto")

        const hold = byName(overlay, "lockHold")
        mousePress(hold)
        fixture.advance(1000)
        verify(fixture.touchLock.holdProgress > 0.6 && fixture.touchLock.holdProgress < 0.7, "ring at " + fixture.touchLock.holdProgress)
        mouseRelease(hold)
        compare(fixture.touchLock.holdProgress, 0)
        verify(fixture.touchLock.locked, "a short press does not unlock")

        mousePress(hold)
        fixture.advance(1500)
        mouseRelease(hold)
        verify(!fixture.touchLock.locked, "1.5 s unlocks")
        verify(!overlay.visible)
        mouseClick(byName(main.contentItem, "tab-numbers"))
        compare(main.page, "numbers")
    }

    function test_lockHoldTargetIsOverTheLockButton() {
        const main = makeMain(1024, 600)
        fixture.touchLock.lockNow()
        const hold = byName(main.contentItem, "lockHold")
        const button = byName(main.contentItem, "lockButton")
        const a = hold.mapToItem(main.contentItem, 0, 0), b = button.mapToItem(main.contentItem, 0, 0)
        verify(Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1, "hold at " + a.x + "," + a.y + " button at " + b.x + "," + b.y)
        verify(hold.width >= Units.mm(12) - 0.5 && hold.height >= Units.mm(12) - 0.5)
    }

    function makeTracks(w, h) {
        const page = createTemporaryObject(tracksComp, testCase,
                                           { width: w, height: h, tracks: fixture.tracksController, settings: fixture.settings })
        verify(page, "TracksPage")
        return page
    }
    function rowTexts(row) {
        return findAll(row, it => it.text !== undefined && it.visible).map(it => it.text).join(" | ")
    }

    function test_tracksConstructsEmptyAndWithRows_data() { return sizes() }
    function test_tracksConstructsEmptyAndWithRows(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const page = makeTracks(data.w - Units.mm(17), data.h)
        verify(byName(page, "recordButton"))
        verify(byName(page, "noTracks").visible, "empty state")
        fixture.addTrack(1.7e9)
        fixture.addTrack(1.7e9 + 86400)
        compare(findAll(page, it => it.objectName === "trackRow").length, 2)
        verify(!byName(page, "noTracks").visible)
        checkBigButtons(page)
    }

    function test_tracksRecordButtonTogglesTheSetting() {
        const page = makeTracks(1200, 800)
        const b = byName(page, "recordButton")
        compare(fixture.settings.trackRecording, false)
        compare(b.text, "Start recording")
        mouseClick(b)
        compare(fixture.settings.trackRecording, true)
        compare(b.text, "Stop recording")
        mouseClick(b)
        compare(fixture.settings.trackRecording, false)
    }

    function test_tracksRowShowsNameDurationAndNauticalMiles() {
        const page = makeTracks(1200, 800)
        fixture.addTrack(1.7e9) // 10 minutes, about 1112 m = 0.6 nm
        const row = byName(page, "trackRow")
        verify(row, "row")
        const text = rowTexts(row)
        verify(text.indexOf("0.6 nm") >= 0, text)
        verify(text.indexOf("10 min") >= 0, text)
        verify(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(text), text)
    }

    function test_tracksShowHideToggle() {
        const page = makeTracks(1200, 800)
        const id = fixture.addTrack(1.7e9)
        const toggle = byName(page, "trackToggle")
        compare(toggle.text, "Hide")
        mouseClick(toggle)
        compare(fixture.tracksController.tracks[0].visible, false)
        compare(fixture.tracksController.tracks[0].id, id)
        compare(byName(page, "trackToggle").text, "Show")
        mouseClick(byName(page, "trackToggle"))
        compare(fixture.tracksController.tracks[0].visible, true)
    }

    function test_tracksDeleteAsksFirstInPage() {
        const page = makeTracks(1200, 800)
        fixture.addTrack(1.7e9)
        const confirm = byName(page, "confirmDelete")
        verify(!confirm.visible)
        mouseClick(byName(page, "trackDelete"))
        verify(confirm.visible, "confirm shown")
        verify(byName(confirm, "confirmYes").width >= Units.mm(12) - 0.5)
        mouseClick(byName(confirm, "confirmNo"))
        verify(!confirm.visible)
        compare(fixture.tracksController.tracks.length, 1)
        mouseClick(byName(page, "trackDelete"))
        mouseClick(byName(confirm, "confirmYes"))
        verify(!confirm.visible)
        compare(fixture.tracksController.tracks.length, 0)
        verify(byName(page, "noTracks").visible)
    }

    function test_tracksTabShowsThePageInMain() {
        const main = makeMain(1024, 600)
        byName(main.contentItem, "splash").visible = false
        mouseClick(byName(main.contentItem, "tab-tracks"))
        verify(byName(main.contentItem, "tracksPage").visible)
        verify(byName(main.contentItem, "recordButton"))
    }

    function test_tabBarRecordIndicatorFollowsTheSetting() {
        const main = makeMain(1024, 600)
        const ind = byName(main.contentItem, "recordIndicator")
        verify(ind, "indicator")
        verify(!ind.visible)
        fixture.settings.trackRecording = true
        verify(ind.visible)
        const tab = byName(main.contentItem, "tab-tracks")
        verify(ind.width < Units.mm(4) && ind.height < Units.mm(4))
        const a = ind.mapToItem(main.contentItem, 0, 0), t = tab.mapToItem(main.contentItem, 0, 0)
        verify(a.x >= t.x && a.x + ind.width <= t.x + tab.width && a.y >= t.y && a.y + ind.height <= t.y + tab.height,
               "indicator sits inside the Tracks tab: it adds no height to the tab column")
    }
}
