import QtQuick
import QtTest
import CheekyMarine
import "Helpers.js" as H

// Pages construct without warnings at both panel sizes, every BigButton is at least 12 mm both
// ways, the no-data banner text, slot digit size, the chart and cell pages drawing the shown view.
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
        readonly property var fullLegend: [{ abbr: "Blds", meaning: "boulders", kind: "type" },
                                           { abbr: "Cb", meaning: "cobbles", kind: "type" },
                                           { abbr: "Sh", meaning: "shells", kind: "type" },
                                           { abbr: "bk", meaning: "broken", kind: "qualifier" }]
        property var legend: fullLegend
        property var aisSelection: ({})
        property var selected: [] // selectAt calls: {x, y, r}
        property var targetPoint: null // targetAt resolves a target within r of this point only
        function targetAt(p, r) {
            return targetPoint && Math.abs(p.x - targetPoint.x) < r && Math.abs(p.y - targetPoint.y) < r
                   ? { mmsi: "367000001" } : undefined
        }
        function selectAt(p, r) { selected.push({ x: p.x, y: p.y, r: r }) }
        function clearTarget() { aisSelection = ({}) }
        function zoomIn() {}
        function zoomOut() {}
        property var zooms: [] // zoomBy calls: log2 deltas
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
    Component { id: chartPageComp; ChartPage {} }
    Component { id: cellPageComp; CellPage {} }
    Component { id: aboutPageComp; AboutPage {} }
    Component { id: recoveryComp; RecoveryScreen {} }
    Component { id: bannerComp; NoDataBanner {} }
    Component { id: slotComp; SlotView {} }
    Component { id: settingsComp; SettingsPage {} }
    Component { id: tracksComp; TracksPage {} }
    Component { id: spyComp; SignalSpy {} }

    readonly property string twoColumns: "2x2:0,0,1,2;1,0,1,2"
    readonly property string quad: "2x2:0,0,1,1;1,0,1,1;0,1,1,1;1,1,1,1"
    readonly property string tallLeft: "2x3:0,0,1,3;1,0,1,1;1,1,1,1;1,2,1,1"

    function init() {
        failOnWarning(/.*/)
        fixture.reset()
        chartStub.legend = chartStub.fullLegend
        chartStub.follow = true
        chartStub.noPosition = false
        chartStub.fishAvailable = true
        chartStub.mode = "nav"
        chartStub.selected = []
        chartStub.targetPoint = null
        chartStub.zooms = []
        Units.windowWidth = 1280
        Units.windowHeight = 800
        Units.diagonalIn = 10.1
    }

    function makeChart(props) {
        const chart = createTemporaryObject(chartPageComp, testCase, Object.assign({
            width: 1280 - Units.mm(17), height: 800,
            chart: chartStub, chartMap: createTemporaryObject(mapStub, testCase), draft: fixture.draft }, props || {}))
        verify(chart, "ChartPage")
        return chart
    }
    function makeCells(props) {
        const page = createTemporaryObject(cellPageComp, testCase, Object.assign({
            width: 1200, height: 800, draft: fixture.draft }, props || {}))
        verify(page, "CellPage")
        return page
    }
    // Loads a stored view into the fixture's draft, as Main does for the current view.
    function showView(id) { fixture.draft.loadJson(fixture.views.viewJson(id)) }
    function spy(target, signalName) {
        return createTemporaryObject(spyComp, testCase, { target: target, signalName: signalName })
    }
    function where(it, ref) { const b = H.box(it, ref); return it.objectName + " " + [b.x, b.y, b.w, b.h].map(Math.round).join(",") }

    // The tallest run of image rows with ink against the background at mid-height: the digit of a
    // slot (the label is shorter and a gap apart, the unit sits beside it). The whole slot is
    // grabbed: the value text item's box reaches above the slot, so a grab of it alone is cut off.
    function inkRows(item) {
        const img = grabImage(item)
        const bg = img.pixel(0, Math.floor(img.height / 2))
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
        return rows
    }

    function test_pagesConstruct_data() { return H.sizes() }
    function test_pagesConstruct(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const props = { width: data.w - Units.mm(17), height: data.h }
        H.checkBigButtons(testCase, Units, makeChart(props))
        showView("shipped-big")
        H.checkBigButtons(testCase, Units, makeCells(props))
        const about = createTemporaryObject(aboutPageComp, testCase, Object.assign({ appInfo: fixture.appInfo }, props))
        verify(about, "AboutPage")
        H.checkBigButtons(testCase, Units, about)
        const rec = createTemporaryObject(recoveryComp, testCase, { width: data.w, height: data.h, recovery: fixture.recovery })
        verify(rec, "RecoveryScreen")
        compare(H.checkBigButtons(testCase, Units, rec), 2) // Start fresh, and Try again for an Io error
    }

    function test_aisSheet() {
        const chart = makeChart()
        const sheet = H.byName(chart, "aisSheet")
        verify(sheet, "aisSheet")
        verify(!sheet.visible)
        chartStub.aisSelection = { mmsi: "367000001", name: "SEA QUEEN", cls: "A", sog: "10.0", cog: "090",
                                   range: "1.0", bearing: "307", posAge: "12 s" }
        verify(sheet.visible)
        const values = H.findAll(sheet, it => it.objectName === "aisValue").map(it => it.text)
        verify(values.indexOf("SEA QUEEN") >= 0, "name")
        verify(values.indexOf("367000001") >= 0, "mmsi")
        compare(values.length, 8)
        compare(H.checkBigButtons(testCase, Units, sheet), 1) // the Close button only
        const close = H.byName(sheet, "aisCloseButton")
        verify(close)
        close.clicked()
        verify(!sheet.visible)
    }

    function test_legendSheet() {
        const chart = makeChart()
        const sheet = H.byName(chart, "legendSheet")
        verify(sheet, "legendSheet")
        verify(!sheet.visible)
        const open = H.byName(chart, "legendButton")
        verify(open && open.isBigButton)
        open.clicked()
        verify(sheet.visible)
        const rows = H.findAll(sheet, it => it.objectName === "legendRow")
        compare(rows.length, chartStub.legend.length)
        for (const r of rows)
            verify(r.height >= Units.mm(12), "row height")
        // The kind reads as a word, not the legend.json key.
        compare(H.findAll(sheet, it => it.objectName === "legendKind").map(it => it.text).sort(),
                ["Qualifier", "Type", "Type", "Type"])
        H.checkBigButtons(testCase, Units, sheet)
        const close = H.byName(sheet, "legendCloseButton")
        verify(close)
        close.clicked()
        verify(!sheet.visible)
    }

    // A tap on the chart (mouse, and touch as on the panel) reaches selectAt with the point in map
    // area coordinates, the ones the map's pixelForCoordinate uses, and an 8 mm radius. The Top and
    // Left bars are on, so the map area is offset from the page and page coordinates would differ.
    function test_chartTapSelectsAtMapAreaPoint() {
        fixture.draft.setSlot("Top", true, "time", 8)
        fixture.draft.setSlot("Left", true, "stw", 14)
        const chart = makeChart()
        waitForRendering(chart)
        const map = H.byName(chart, "mapArea")
        verify(map.x > 0 && map.y > 0, "map area offset by the bars")
        mouseClick(map, 300, 250)
        touchEvent(map).press(0, map, 400, 350).commit()
        touchEvent(map).release(0, map, 400, 350).commit()
        const want = [{ x: 300, y: 250 }, { x: 400, y: 350 }]
        compare(chartStub.selected.length, want.length)
        for (let i = 0; i < want.length; ++i) {
            const got = chartStub.selected[i], what = JSON.stringify(got)
            verify(Math.abs(got.x - want[i].x) < 1 && Math.abs(got.y - want[i].y) < 1, what)
            fuzzyCompare(got.r, Units.mm(8), 1e-6)
        }
    }

    // A tap that resolves to a target selects it and is not a plain tap; a tap on empty chart is
    // both (selectAt leaves the selection alone on a miss) and fires plainTap once.
    function test_plainTapOnlyWhenNoTarget() {
        chartStub.targetPoint = { x: 300, y: 250 }
        const chart = makeChart()
        waitForRendering(chart)
        const plain = spy(chart, "plainTap")
        const map = H.byName(chart, "mapArea")
        mouseClick(map, 300, 250)
        compare(chartStub.selected.length, 1)
        compare(plain.count, 0, "a tap on a target is not a plain tap")
        mouseClick(map, 600, 500)
        compare(chartStub.selected.length, 2, "selectAt still runs")
        compare(plain.count, 1)
    }

    // R25: wheel and pinch while following zoom through the controller (about the boat) and keep
    // follow; not following, they scale the map about the point. Only a pan ends follow.
    function test_chartZoomGesturesKeepFollow() {
        const mapItem = createTemporaryObject(mapStub, testCase)
        const chart = makeChart({ chartMap: mapItem })
        waitForRendering(chart)
        const map = H.byName(chart, "mapArea")
        mouseWheel(map, 300, 300, 0, 120)
        compare(chartStub.zooms.length, 1)
        fuzzyCompare(chartStub.zooms[0], 0.5, 1e-9)
        touchEvent(map).press(0, map, 300, 300).press(1, map, 400, 300).commit()
        for (let i = 1; i <= 10; ++i)
            touchEvent(map).move(0, map, 300 - 10 * i, 300).move(1, map, 400 + 10 * i, 300).commit()
        touchEvent(map).release(0, map, 200, 300).release(1, map, 500, 300).commit()
        verify(chartStub.zooms.length > 1, "pinch zooms through the controller")
        verify(chartStub.zooms.slice(1).every(d => d > 0), "spreading fingers zooms in")
        compare(mapItem.gestures, 0)
        compare(mapItem.scales.length, 0)

        chartStub.follow = false
        const n = chartStub.zooms.length
        mouseWheel(map, 300, 300, 0, -120)
        compare(mapItem.scales.length, 1)
        fuzzyCompare(mapItem.scales[0], Math.pow(2, -0.5), 1e-9)
        compare(chartStub.zooms.length, n)

        chartStub.follow = true
        mouseDrag(map, 300, 300, 120, 0)
        compare(mapItem.gestures, 1, "a pan ends follow")
        verify(mapItem.moves > 0)
    }

    // No legend (no pack, or no legend.json): no button that would open a blank sheet.
    function test_legendButtonHiddenWhenLegendEmpty() {
        const chart = makeChart()
        const button = H.byName(chart, "legendButton")
        verify(button.visible)
        chartStub.legend = []
        verify(!button.visible)
    }

    // The shipped Navigation view: depth and SOG in the top corners at 25 mm, the rest off.
    function test_chartPageRendersDraftSlots_data() { return H.sizes() }
    function test_chartPageRendersDraftSlots(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        fixture.setVessel(8 * 0.3048, 0)
        const chart = makeChart({ width: data.w, height: data.h, rightInset: Units.mm(17) })
        waitForRendering(chart)
        const shown = H.findAll(chart, it => it.objectName.startsWith("slot-") && it.visible).map(it => it.objectName)
        compare(shown.sort(), ["slot-TL", "slot-TR"])
        const tl = H.byName(chart, "slot-TL")
        compare(tl.formatted, "8.0")
        compare(tl.sizeMm, 25)
        const want = Units.mm(25)
        const rows = inkRows(tl)
        verify(rows >= want * 0.95, "8 is " + rows + " px tall, want " + want * 0.95)
        verify(rows <= want * 1.1, "8 is " + rows + " px tall, want about " + want)
    }

    // TR and BR both large: the least room for the zoom column between them. The last row puts the
    // live two-line position in TR over a large BR: less room between the right corners than the
    // column needs, so it has to go beside them. Every slot is drawn at the clamped size, so none
    // overlaps another or leaves the page, whatever the stored sizes.
    function test_allSlotsOnFitWithoutOverlap_data() {
        const both = [25, 25, 14, 25, 8, 8, 14, 14]
        const fields = ["depth", "sog", "cog", "wtemp", "time", "pos", "stw", "hdg"]
        return H.sizes().map(s => Object.assign({ fields: fields, sizes: both }, s)).concat([
            { tag: "1024x600 position in TR", w: 1024, h: 600, position: true,
              fields: ["depth", "pos", "cog", "wtemp", "time", "sog", "stw", "hdg"], sizes: both.map((z, i) => i === 1 ? 14 : z) }])
    }
    function test_allSlotsOnFitWithoutOverlap(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        if (data.position) fixture.setPosition(47.98, -122.23)
        const ids = ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"]
        for (let i = 0; i < ids.length; ++i)
            fixture.draft.setSlot(ids[i], true, data.fields[i], data.sizes[i])
        // Every chart control on: recenter (not following) and the no-position chip too (not with a
        // live position).
        chartStub.follow = false
        chartStub.noPosition = !data.position
        const chart = makeChart({ width: data.w, height: data.h, rightInset: Units.mm(17) })
        waitForRendering(chart)
        const right = chart.width - chart.rightInset
        const inside = it => {
            const b = H.box(it, chart)
            return b.x >= -0.5 && b.y >= -0.5 && b.x + b.w <= right + 0.5 && b.y + b.h <= chart.height + 0.5
        }
        const slots = H.findAll(chart, it => it.objectName.startsWith("slot-") && it.visible)
        compare(slots.length, 8)
        for (let a = 0; a < slots.length; ++a) {
            verify(inside(slots[a]), where(slots[a], chart) + " is outside the page")
            for (let b = a + 1; b < slots.length; ++b)
                verify(!H.overlaps(slots[a], slots[b], chart), where(slots[a], chart) + " overlaps " + where(slots[b], chart))
        }
        // The chart's controls clear every slot and each other, and stay inside the page.
        const controls = H.findAll(chart, it => it.isBigButton === true && it.visible && !it.objectName.startsWith("slot-"))
                         .concat([H.byName(chart, "noPositionChip")].filter(it => it.visible))
        compare(controls.map(c => c.objectName).sort(),
                ["legendButton"].concat(data.position ? [] : ["noPositionChip"],
                                        ["recenterButton", "zoomInButton", "zoomOutButton"]))
        for (let a = 0; a < controls.length; ++a) {
            verify(inside(controls[a]), where(controls[a], chart) + " is outside the page")
            for (const s of slots)
                verify(!H.overlaps(controls[a], s, chart), where(controls[a], chart) + " overlaps " + where(s, chart))
            for (let b = a + 1; b < controls.length; ++b)
                verify(!H.overlaps(controls[a], controls[b], chart), where(controls[a], chart) + " overlaps " + where(controls[b], chart))
        }
        // Bars shrink the viewport: the map area lies between them.
        const map = H.byName(chart, "mapArea")
        const top = H.byName(chart, "slot-Top"), left = H.byName(chart, "slot-Left")
        verify(map.y >= top.height - 0.5, "map below the top bar")
        verify(map.x >= left.width - 0.5, "map right of the left bar")
    }

    // A 7 in panel (many px per mm, so few mm of page) with every slot at 25 mm: the side bars stay
    // between the banners and no slot overlaps another or leaves the page.
    function test_sideBarsClearTheBannersOnASmallPanel_data() { return H.sizes() }
    function test_sideBarsClearTheBannersOnASmallPanel(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        Units.diagonalIn = 7
        const ids = ["TL", "TR", "BL", "BR", "Top", "Bottom", "Left", "Right"]
        const fields = ["depth", "sog", "cog", "wtemp", "time", "pos", "stw", "hdg"]
        for (let i = 0; i < ids.length; ++i)
            fixture.draft.setSlot(ids[i], true, fields[i], 25)
        const chart = makeChart({ width: data.w, height: data.h, rightInset: Units.mm(17) })
        waitForRendering(chart)
        const slots = H.findAll(chart, it => it.objectName.startsWith("slot-") && it.visible)
        compare(slots.length, 8)
        for (const side of ["slot-Left", "slot-Right"])
            for (const banner of ["slot-Top", "slot-Bottom"]) {
                const a = H.byName(chart, side), b = H.byName(chart, banner)
                verify(!H.overlaps(a, b, chart), where(a, chart) + " overlaps " + where(b, chart))
            }
        const right = chart.width - chart.rightInset
        for (let a = 0; a < slots.length; ++a) {
            const b = H.box(slots[a], chart)
            verify(b.x >= -0.5 && b.y >= -0.5 && b.x + b.w <= right + 0.5 && b.y + b.h <= chart.height + 0.5,
                   where(slots[a], chart) + " is outside the page")
            for (let c = a + 1; c < slots.length; ++c)
                verify(!H.overlaps(slots[a], slots[c], chart), where(slots[a], chart) + " overlaps " + where(slots[c], chart))
        }
    }

    // Review Focus 2: a stored size too big for the page is drawn clamped, and the stored size stays.
    function drawnTopCorners(w, h) {
        Units.windowWidth = w
        Units.windowHeight = h
        const chart = makeChart({ width: w, height: h, rightInset: Units.mm(17) })
        waitForRendering(chart)
        const tl = H.byName(chart, "slot-TL"), tr = H.byName(chart, "slot-TR"), area = H.byName(chart, "cornerArea")
        verify(!H.overlaps(tl, tr, chart), where(tl, chart) + " overlaps " + where(tr, chart))
        const a = H.box(area, chart)
        for (const s of [tl, tr]) {
            const b = H.box(s, chart)
            verify(b.x >= a.x - 0.5 && b.y >= a.y - 0.5 && b.x + b.w <= a.x + a.w + 0.5 && b.y + b.h <= a.y + a.h + 0.5,
                   where(s, chart) + " is outside the corner area " + where(area, chart))
            compare(s.sizeMm, 90)
            verify(s.drawnMm >= 6 && s.drawnMm < 90, s.objectName + " drawn at " + s.drawnMm)
            compare(H.byName(s, "slotValue").font.pixelSize, Units.digitPixelSize(s.drawnMm))
        }
        // Both stored at 90: the row is shared by one factor, so they draw at the same size (R64).
        verify(Math.abs(tl.drawnMm - tr.drawnMm) <= 0.1 + 1e-9, "TL " + tl.drawnMm + " vs TR " + tr.drawnMm)
        return { mm: [tl.drawnMm, tr.drawnMm], px: [Units.mm(tl.drawnMm), Units.mm(tr.drawnMm)] }
    }
    function test_storedSizeAboveTheCeilingIsClampedNotRewritten() {
        fixture.draft.setSlot("TL", true, "depth", 90)
        fixture.draft.setSlot("TR", true, "sog", 90)
        const small = drawnTopCorners(1024, 600)
        const big = drawnTopCorners(1280, 800)
        const stored = fixture.draft.toJson().slots.filter(s => s.id === "TL" || s.id === "TR").map(s => s.sizeMm)
        compare(stored, [90, 90])
        // Both panels are 10.1 in, and 1280x800 is the narrower one in mm, so a width-bound slot is
        // drawn a little smaller in mm there; on screen (in pixels) it is drawn larger.
        verify(big.px[0] > small.px[0] && big.px[1] > small.px[1], "1280x800 " + big.px + " px vs 1024x600 " + small.px + " px")
    }

    // The bars and the corner area stop at the strip; the map runs under it.
    function test_barsStopAtTheInset() {
        fixture.draft.setSlot("Top", true, "time", 8)
        const chart = makeChart({ width: 1200, height: 800, rightInset: 80 })
        waitForRendering(chart)
        const top = H.byName(chart, "slot-Top")
        verify(top.visible)
        compare(top.width, chart.width - 80)
        compare(H.byName(chart, "mapArea").width, chart.width)
        const area = H.byName(chart, "cornerArea")
        verify(area.x + area.width <= chart.width - 80 - Units.mm(1.5) + 0.5, where(area, chart))
        fixture.draft.setSlot("Right", true, "hdg", 14)
        const right = H.byName(chart, "slot-Right")
        verify(right.visible)
        fuzzyCompare(right.x + right.width, chart.width - 80, 0.5)
        verify(area.x + area.width <= right.x - Units.mm(1.5) + 0.5, where(area, chart) + " runs into " + where(right, chart))
    }

    // Review Focus 1: a Fishing view with no bathy pack says so; there is no mode button.
    function test_fishWithoutBathyShowsChip() {
        chartStub.fishAvailable = false
        showView("shipped-fish")
        const chart = makeChart()
        const chip = H.byName(chart, "noFishChip")
        verify(chip.visible)
        compare(chip.text, "No fishing chart installed")
        chartStub.fishAvailable = true
        verify(!chip.visible)
        chartStub.fishAvailable = false
        showView("shipped-nav")
        verify(!chip.visible, "only a fishing view")
        compare(H.byName(chart, "modeButton"), null)
    }

    function test_editingOutlinesAndTapsEmitSlotId() {
        const chart = makeChart({ width: 1200, height: 800 })
        chart.editing = true
        const slots = H.findAll(chart, it => it.objectName.startsWith("slot-") && it.visible)
        compare(slots.length, 8)
        for (const s of slots) {
            verify(s.background.border.width > 0, s.objectName + " outlined")
            const name = H.byName(s, "slotPosition")
            if (s.on) {
                verify(!name.visible, s.objectName)
            } else {
                verify(name.visible, s.objectName)
                compare(name.text, s.slotId)
            }
        }
        const tapped = spy(chart, "slotTapped")
        mouseClick(H.byName(chart, "slot-BL"))
        compare(tapped.count, 1)
        compare(tapped.signalArguments[0][0], "BL")
    }

    // A slot box is never bigger than its coefficients say at the drawn size (the clamp's model of
    // it), and with the widest value it is that size within 1 mm.
    function test_slotBoxWithinItsCoefficients_data() {
        let out = []
        for (const s of H.sizes())
            for (const c of [{ id: "TL", field: "depth", label: "Depth", unit: "ft", sample: "9999.9", mm: 25 },
                             { id: "BR", field: "wtemp", label: "Water temp", unit: "°F", sample: "999.9", mm: 6 },
                             { id: "TR", field: "pos", label: "Position", unit: "", sample: "89°59.999'N\n122°59.999'W", mm: 14 },
                             { id: "Top", field: "pos", label: "Position", unit: "", sample: "89°59.999'N\n122°59.999'W", mm: 8 },
                             { id: "Left", field: "stw", label: "STW", unit: "kn", sample: "99.9", mm: 14 }])
                out.push(Object.assign({ tag: s.tag + " " + c.id + " " + c.field, w: s.w, h: s.h }, c))
        return out
    }
    function test_slotBoxWithinItsCoefficients(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const slot = createTemporaryObject(slotComp, testCase, {
            slotId: data.id, on: true, field: data.field, fieldLabel: data.label, sizeMm: data.mm,
            formatted: data.sample, unit: data.unit, widestSample: data.sample })
        waitForRendering(slot)
        const w = (slot.fixedWMm + slot.wPerMm * slot.drawnMm) * Units.pxPerMm
        const h = (slot.fixedHMm + slot.hPerMm * slot.drawnMm) * Units.pxPerMm
        verify(slot.implicitWidth <= w + 0.5 && slot.implicitWidth >= w - Units.mm(1),
               "width " + slot.implicitWidth + " px, coefficients say " + w)
        verify(slot.implicitHeight <= h + 0.5 && slot.implicitHeight >= h - Units.mm(1),
               "height " + slot.implicitHeight + " px, coefficients say " + h)
    }

    // Big numbers: two columns, the quad and the tall-left 2x3, 1 mm gaps, the strip left free.
    function test_cellPageLaysOutTheLayout_data() { return H.sizes() }
    function test_cellPageLaysOutTheLayout(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        showView("shipped-big")
        compare(fixture.draft.layout, twoColumns)
        const page = makeCells({ width: data.w, height: data.h, rightInset: Units.mm(17) })
        const g = Units.mm(1), W = page.width - page.rightInset, H2 = page.height
        const cells = () => H.findAll(page, it => it.objectName.startsWith("cell-") && it.visible)
                            .sort((a, b) => a.objectName.localeCompare(b.objectName))
        const near = (a, b, what) => verify(Math.abs(a - b) <= 1, what + ": " + a + " vs " + b)

        let c = cells()
        compare(c.length, 2)
        for (const cell of c) {
            near(cell.width, (W - 3 * g) / 2, cell.objectName + " width")
            near(cell.height, H2 - 2 * g, cell.objectName + " height")
        }
        near(c[0].x, g, "left gap")
        near(c[1].y, c[0].y, "side by side")
        near(c[1].x, c[0].x + c[0].width + g, "gap between")
        near(c[1].x + c[1].width, W - g, "right edge at the strip")

        fixture.draft.layout = quad
        c = cells()
        compare(c.length, 4)
        for (const cell of c) {
            near(cell.width, (W - 3 * g) / 2, cell.objectName + " width")
            near(cell.height, (H2 - 3 * g) / 2, cell.objectName + " height")
        }
        near(c[0].y, c[1].y, "first row")
        near(c[2].y, c[3].y, "second row")
        near(c[2].y, c[0].y + c[0].height + g, "rows a gap apart")
        near(c[2].x, c[0].x, "columns")

        fixture.draft.layout = tallLeft
        c = cells()
        compare(c.length, 4)
        near(c[0].height, H2 - 2 * g, "cell-0 full height")
        near(c[0].width, (W - 3 * g) / 2, "cell-0 width")
        for (let i = 1; i < 4; ++i) {
            near(c[i].x, c[0].x + c[0].width + g, c[i].objectName + " on the right")
            near(c[i].height, (H2 - 4 * g) / 3, c[i].objectName + " height")
            if (i > 1) near(c[i].y, c[i - 1].y + c[i - 1].height + g, c[i].objectName + " stacked")
        }
    }

    function test_cellPageDigitsFollowVesselAndUnits() {
        showView("shipped-big")
        const page = makeCells()
        const c0 = H.byName(page, "cell-0"), c1 = H.byName(page, "cell-1")
        compare(c0.fieldLabel, "Depth")
        compare(c1.fieldLabel, "SOG")
        compare(c0.formatted, "--")
        fixture.setVessel(3 * 0.3048, 0)
        compare(c0.formatted, "3.0")
        compare(c0.unit, "ft")
        fixture.settings.depthUnit = "m"
        compare(c0.formatted, "0.9")
        compare(c0.unit, "m")
        compare(c1.unit, "kn")
    }

    function test_cellEditingTapsEmitIndex() {
        showView("shipped-big")
        const page = makeCells({ rightInset: 80 })
        const tapped = spy(page, "cellTapped"), plain = spy(page, "plainTap")
        const c1 = H.byName(page, "cell-1")
        mouseClick(c1)
        compare(tapped.count, 0)
        compare(plain.count, 1, "a cell tap while not editing is a plain tap")
        page.editing = true
        verify(c1.background.border.width >= 2, "outlined")
        mouseClick(c1)
        compare(tapped.count, 1)
        compare(tapped.signalArguments[0][0], 1)
        compare(plain.count, 1)
        page.editing = false
        mouseClick(page, page.width - 40, page.height / 2) // the background under the strip
        compare(plain.count, 2)
    }

    // The QML faces of Tilings.h and favouriteCapacity.
    function test_layoutsAndCapacityForQml() {
        const g = Layouts.gallery()
        compare(g.length, 72)
        compare(g[0].cells, 1)
        compare(g[0].rects, Layouts.rects(g[0].key))
        verify(g.every((e, i) => i === 0 || e.cells >= g[i - 1].cells), "ordered by cell count")
        compare(Layouts.rects(twoColumns), [{ x: 0, y: 0, w: 0.5, h: 1 }, { x: 0.5, y: 0, w: 0.5, h: 1 }])
        compare(Layouts.rects("not a layout"), [])
        compare(PanelMath.favouriteCapacity(110), 4)
        compare(PanelMath.favouriteCapacity(40), 0)
    }

    // The charts line tells "nothing installed" from "installed but refused" (the About page lists
    // refusals with reasons).
    Component { id: splashComp; Splash {} }
    QtObject {
        id: appInfoStub
        property string appVersion: "0.1.0"
        property var chartsPack: ({})
        property var bathyPack: ({})
        property var packs: []
    }
    function test_splashChartsLine_data() {
        const ok = { kind: "charts", region: "puget-north", version: "1.0.0", notice: "", refused: "", inUse: true }
        const bad = { kind: "charts", region: "puget-north", version: "2.0.0", notice: "", refused: "styles/nav-day.json: bad", inUse: false }
        const bathy = { kind: "bathy", region: "puget-north", version: "1.0.0", notice: "", refused: "", inUse: false }
        return [
            { tag: "in use", charts: ok, packs: [ok, bad], want: "Charts: puget-north 1.0.0" },
            { tag: "all refused", charts: ({}), packs: [bad, bathy], want: "Charts pack refused: see Settings, About" },
            { tag: "none", charts: ({}), packs: [bathy], want: "No charts pack installed" },
            { tag: "no packs", charts: ({}), packs: [], want: "No charts pack installed" }
        ]
    }
    function test_splashChartsLine(data) {
        appInfoStub.chartsPack = data.charts
        appInfoStub.packs = data.packs
        const splash = createTemporaryObject(splashComp, testCase, { width: 1024, height: 600, appInfo: appInfoStub })
        compare(H.byName(splash, "splashCharts").text, data.want)
    }
    // The same for the fishing chart: a refused bathy pack is not "not installed".
    function test_splashBathyLine_data() {
        const ok = { kind: "bathy", region: "puget-north", version: "1.0.0", notice: "", refused: "", inUse: true }
        const bad = { kind: "bathy", region: "puget-north", version: "2.0.0", notice: "", refused: "styles/fish-day.json: bad", inUse: false }
        const charts = { kind: "charts", region: "puget-north", version: "1.0.0", notice: "", refused: "", inUse: true }
        return [
            { tag: "in use", bathy: ok, packs: [charts, ok, bad], want: "Bathy: puget-north 1.0.0" },
            { tag: "refused", bathy: ({}), packs: [charts, bad], want: "Bathy pack refused: see Settings, About" },
            { tag: "none", bathy: ({}), packs: [charts], want: "No fishing chart installed" }
        ]
    }
    function test_splashBathyLine(data) {
        appInfoStub.chartsPack = ({})
        appInfoStub.bathyPack = data.bathy
        appInfoStub.packs = data.packs
        const splash = createTemporaryObject(splashComp, testCase, { width: 1024, height: 600, appInfo: appInfoStub })
        compare(H.byName(splash, "splashBathy").text, data.want)
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

    // The digit ratio is measured on the loaded bold face, not a fallback or a synthesized bold.
    FontMetrics { id: boldMetrics; font.family: Units.fontFamily; font.bold: true; font.pixelSize: 200 }
    function test_digitRatioMeasuredOnLoadedFonts() {
        compare(Units.regularFont.status, FontLoader.Ready)
        compare(Units.boldFont.status, FontLoader.Ready)
        verify(Units.fontsReady)
        compare(Units.boldFont.name, Units.fontFamily) // one family: Bold is its bold face
        fuzzyCompare(Units.digitRatio, boldMetrics.tightBoundingRect("8").height / 200, 1e-9)
        verify(Units.digitRatio > 0.68 && Units.digitRatio < 0.75, "Noto Sans Bold 8 is about 0.71 em: " + Units.digitRatio)
    }

    // Width per mm of digit height, on the same face; a two-line text takes its wider line.
    function test_textWidthPerDigitMm() {
        const per = text => boldMetrics.advanceWidth(text) / (200 * Units.digitRatio)
        fuzzyCompare(Units.textWidthPerDigitMm("9999.9"), per("9999.9"), 1e-9)
        verify(Units.textWidthPerDigitMm("9999.9") > Units.textWidthPerDigitMm("99.9"))
        fuzzyCompare(Units.textWidthPerDigitMm("89°59.999'N\n122°59.999'W"), per("122°59.999'W"), 1e-9)
        compare(Units.digitMm, undefined)
        compare(Units.slotDigitMm, undefined)
    }

    // A slot's "8" is drawn at its digit height in mm (95 to 110 %), at both panel sizes.
    function test_slotDigitHeight_data() {
        let out = []
        for (const s of H.sizes())
            for (const mm of [8, 14, 25])
                out.push({ tag: s.tag + " " + mm + " mm", w: s.w, h: s.h, mm: mm })
        return out
    }
    function test_slotDigitHeight(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const want = Units.mm(data.mm)
        const slot = createTemporaryObject(slotComp, testCase, {
            x: 20, y: 20, slotId: "TL", on: true, field: "depth", fieldLabel: "Depth", sizeMm: data.mm,
            formatted: "8", unit: "ft", widestSample: "9999.9" })
        verify(H.byName(slot, "slotValue"))
        compare(slot.drawnMm, data.mm)
        waitForRendering(slot)
        const rows = inkRows(slot)
        verify(rows >= want * 0.95, "8 is " + rows + " px tall, want " + want * 0.95)
        verify(rows <= want * 1.1, "8 is " + rows + " px tall, want about " + want)
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
        tap(H.byName(page, row))
        waitForRendering(H.byName(page, "settingsList")) // the list lays out on the next frame
        tap(H.byName(page, "choice-" + choice))
    }

    function test_settingsConstructs_data() { return H.sizes() }
    function test_settingsConstructs(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const page = createTemporaryObject(settingsComp, testCase, { width: data.w - Units.mm(17), height: data.h, settings: fixture.settings })
        verify(page, "SettingsPage")
        H.checkBigButtons(testCase, Units, page)
        verify(H.byName(page, "aboutButton"))
        compare(H.byName(page, "editOverlaysButton"), null)
        compare(H.byName(page, "row-touchLock"), null)
    }

    function test_settingsInvalidDepthShowsReasonAndIsNotSaved() {
        const page = makeSettings()
        const deep = fixture.settings.deepM
        verify(fixture.settings.setDepths(1.8288, deep - 0.3048, deep)) // safety is deep minus 1 ft
        const before = fixture.settings.safetyM
        verify(!H.byName(page, "depthError").visible)
        tap(H.byName(page, "safetyPlus"))
        compare(fixture.settings.safetyM, before)
        verify(H.byName(page, "depthError").visible)
        compare(H.byName(page, "depthError").text, "Safety must be less than deep.")
        tap(H.byName(page, "safetyMinus"))
        verify(fixture.settings.safetyM < before)
        verify(!H.byName(page, "depthError").visible)
    }

    function test_settingsDepthStepFollowsUnit() {
        const page = makeSettings()
        compare(H.byName(page, "shallowValue").text, "6 ft")
        tap(H.byName(page, "shallowPlus"))
        compare(H.byName(page, "shallowValue").text, "7 ft")
        fuzzyCompare(fixture.settings.shallowM, 7 * 0.3048, 1e-6)
        pick(page, "row-depthUnit", "m")
        compare(fixture.settings.depthUnit, "m")
        verify(H.byName(page, "safetyValue").text.endsWith(" m"), H.byName(page, "safetyValue").text)
        const m0 = fixture.settings.deepM
        tap(H.byName(page, "deepPlus"))
        fuzzyCompare(fixture.settings.deepM, m0 + 0.5, 1e-6)
        pick(page, "row-depthUnit", "fm")
        verify(H.byName(page, "safetyValue").text.endsWith(" fm"))
        const f0 = fixture.settings.deepM
        tap(H.byName(page, "deepMinus"))
        fuzzyCompare(fixture.settings.deepM, f0 - 0.9144, 1e-6)
    }

    // At a limit a further step is refused, and the reason is worded in the page's depth unit.
    function test_settingsDepthLimits_data() {
        return [{ tag: "ft", unit: "ft", min: "2 ft", max: "197 ft" },
                { tag: "m", unit: "m", min: "0.5 m", max: "60.0 m" },
                { tag: "fm", unit: "fm", min: "0.3 fm", max: "32.8 fm" }]
    }
    function test_settingsDepthLimits(data) {
        const page = makeSettings()
        fixture.settings.depthUnit = data.unit
        verify(fixture.settings.setDepths(0.5, 1.0, 60.0))
        const error = H.byName(page, "depthError")
        tap(H.byName(page, "deepPlus"))
        compare(fixture.settings.deepM, 60.0)
        verify(error.visible)
        compare(error.text, "Depths must be at most " + data.max + ".")
        compare(H.byName(page, "deepValue").text, data.max)
        tap(H.byName(page, "deepMinus"))
        verify(!error.visible)
        tap(H.byName(page, "shallowMinus"))
        compare(fixture.settings.shallowM, 0.5)
        verify(error.visible)
        compare(error.text, "Depths must be at least " + data.min + ".")
        compare(H.byName(page, "shallowValue").text, data.min)
    }

    // A step that would pass a limit lands on it, so 60 m and 0.5 m are reachable in feet.
    function test_settingsDepthStepClampsToLimit() {
        const page = makeSettings()
        verify(fixture.settings.setDepths(2 * 0.3048, 3.048, 196 * 0.3048))
        compare(H.byName(page, "deepValue").text, "196 ft")
        tap(H.byName(page, "deepPlus"))
        compare(fixture.settings.deepM, 60.0)
        compare(H.byName(page, "deepValue").text, "197 ft")
        verify(!H.byName(page, "depthError").visible)
        tap(H.byName(page, "shallowMinus"))
        compare(fixture.settings.shallowM, 0.5)
        compare(H.byName(page, "shallowValue").text, "2 ft")
        verify(!H.byName(page, "depthError").visible)
    }

    // Switching units only changes the words: the stored metres stay, and ft to m to fm to ft
    // shows the same values again.
    function test_settingsDepthUnitRoundTrip() {
        const page = makeSettings()
        const texts = () => ["shallowValue", "safetyValue", "deepValue"].map(n => H.byName(page, n).text)
        compare(texts(), ["6 ft", "10 ft", "30 ft"])
        pick(page, "row-depthUnit", "m")
        compare(texts(), ["1.8 m", "3.0 m", "9.1 m"])
        pick(page, "row-depthUnit", "fm")
        compare(texts(), ["1.0 fm", "1.7 fm", "5.0 fm"])
        pick(page, "row-depthUnit", "ft")
        compare(texts(), ["6 ft", "10 ft", "30 ft"])
        compare([fixture.settings.shallowM, fixture.settings.safetyM, fixture.settings.deepM], [1.8288, 3.048, 9.144])
    }

    function test_settingsChoiceRows_data() {
        return [
            { row: "row-speedUnit", choice: "kmh", key: "speedUnit", want: "kmh" },
            { row: "row-tempUnit", choice: "C", key: "tempUnit", want: "C" },
            { row: "row-orientation", choice: "north", key: "orientation", want: "north" },
            { row: "row-orientation", choice: "course", key: "orientation", want: "course" },
            { row: "row-paletteMode", choice: "night", key: "paletteMode", want: "night" },
            { row: "row-tabBarHide", choice: "15", key: "tabBarHideS", want: 15,
              labels: ["Off", "5 s", "8 s", "15 s", "30 s"], rowText: "Hide tab bar after: 15 s" },
            { row: "row-tabBarHide", choice: "0", key: "tabBarHideS", want: 0 },
            { row: "row-trackInterval", choice: "30", key: "trackIntervalS", want: 30 },
            { row: "row-trackDistance", choice: "25", key: "trackMinDistanceM", want: 25 }
        ]
    }
    function test_settingsChoiceRows(data) {
        const page = makeSettings()
        if (data.labels) {
            tap(H.byName(page, data.row))
            const list = H.byName(page, "settingsList")
            compare(list.choices.map(c => c.label), data.labels)
            mouseClick(H.byName(page, "listDone"))
        }
        pick(page, data.row, data.choice)
        compare(fixture.settings[data.key], data.want)
        verify(!H.byName(page, "settingsList").visible)
        if (data.rowText) compare(H.byName(page, data.row).text, data.rowText)
    }

    function test_settingsOffsetToggleAndDiagonal() {
        const page = makeSettings()
        const on = fixture.settings.applyDepthOffset
        tap(H.byName(page, "row-applyOffset"))
        compare(fixture.settings.applyDepthOffset, !on)
        compare(H.byName(page, "diagonalValue").text, "10.1 in")
        tap(H.byName(page, "diagonalPlus"))
        compare(fixture.settings.panelDiagonalIn, 10.2)
        tap(H.byName(page, "diagonalMinus"))
        tap(H.byName(page, "diagonalMinus"))
        compare(fixture.settings.panelDiagonalIn, 10.0)
        fixture.settings.panelDiagonalIn = 7.0
        tap(H.byName(page, "diagonalMinus"))
        compare(fixture.settings.panelDiagonalIn, 7.0)
        fixture.settings.panelDiagonalIn = 15.0
        tap(H.byName(page, "diagonalPlus"))
        compare(fixture.settings.panelDiagonalIn, 15.0)
    }

    function test_settingsChartNoticeToggle() {
        const page = makeSettings()
        const row = H.byName(page, "row-chartNotice")
        verify(row, "row-chartNotice")
        compare(row.text, "Chart notice: On")
        tap(row)
        verify(!fixture.settings.showChartNotice)
        compare(row.text, "Chart notice: Off")
        tap(row)
        verify(fixture.settings.showChartNotice)
        compare(row.text, "Chart notice: On")
        const hide = H.byName(page, "row-tabBarHide")
        const kids = hide.parent.children
        let i = 0
        while (kids[i] !== hide) ++i
        compare(kids[i + 1], row, "right after the Hide tab bar row")
    }

    function test_settingsShowsChartDepthNote() {
        const page = makeSettings()
        verify(H.findAll(page, it => it.text === "Chart depths are in feet").length === 1)
    }

    function makeTracks(w, h) {
        const page = createTemporaryObject(tracksComp, testCase,
                                           { width: w, height: h, tracks: fixture.tracksController, settings: fixture.settings })
        verify(page, "TracksPage")
        return page
    }
    function rowTexts(row) {
        return H.findAll(row, it => it.text !== undefined && it.visible).map(it => it.text).join(" | ")
    }

    function test_tracksConstructsEmptyAndWithRows_data() { return H.sizes() }
    function test_tracksConstructsEmptyAndWithRows(data) {
        Units.windowWidth = data.w
        Units.windowHeight = data.h
        const page = makeTracks(data.w - Units.mm(17), data.h)
        verify(H.byName(page, "recordButton"))
        verify(H.byName(page, "noTracks").visible, "empty state")
        fixture.addTrack(1.7e9)
        fixture.addTrack(1.7e9 + 86400)
        compare(H.findAll(page, it => it.objectName === "trackRow").length, 2)
        verify(!H.byName(page, "noTracks").visible)
        H.checkBigButtons(testCase, Units, page)
    }

    function test_tracksRecordButtonTogglesTheSetting() {
        const page = makeTracks(1200, 800)
        const b = H.byName(page, "recordButton")
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
        const row = H.byName(page, "trackRow")
        verify(row, "row")
        const text = rowTexts(row)
        verify(text.indexOf("0.6 nm") >= 0, text)
        verify(text.indexOf("10 min") >= 0, text)
        verify(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(text), text)
    }

    function test_tracksShowHideToggle() {
        const page = makeTracks(1200, 800)
        const id = fixture.addTrack(1.7e9)
        const toggle = H.byName(page, "trackToggle")
        compare(toggle.text, "Hide")
        mouseClick(toggle)
        compare(fixture.tracksController.tracks[0].visible, false)
        compare(fixture.tracksController.tracks[0].id, id)
        compare(H.byName(page, "trackToggle").text, "Show")
        mouseClick(H.byName(page, "trackToggle"))
        compare(fixture.tracksController.tracks[0].visible, true)
    }

    function test_tracksDeleteAsksFirstInPage() {
        const page = makeTracks(1200, 800)
        fixture.addTrack(1.7e9)
        const confirm = H.byName(page, "confirmDelete")
        verify(!confirm.visible)
        mouseClick(H.byName(page, "trackDelete"))
        verify(confirm.visible, "confirm shown")
        verify(H.byName(confirm, "confirmYes").width >= Units.mm(12) - 0.5)
        mouseClick(H.byName(confirm, "confirmNo"))
        verify(!confirm.visible)
        compare(fixture.tracksController.tracks.length, 1)
        mouseClick(H.byName(page, "trackDelete"))
        mouseClick(H.byName(confirm, "confirmYes"))
        verify(!confirm.visible)
        compare(fixture.tracksController.tracks.length, 0)
        verify(H.byName(page, "noTracks").visible)
    }
}

