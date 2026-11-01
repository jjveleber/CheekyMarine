import QtQuick
import QtTest
import CheekyMarine

TestCase {
    id: testCase
    name: "Theme"
    width: 400
    height: 400
    visible: true
    when: windowShown

    Component {
        id: iconComp
        Icon {}
    }
    Component {
        id: iconBoxComp
        Rectangle {
            color: "black"
            property alias icon: iconItem
            Icon { id: iconItem; anchors.centerIn: parent }
        }
    }

    // A color property turns a colour string into channels.
    property color probe

    function channels(value) {
        probe = value
        return { r: Math.round(probe.r * 255), g: Math.round(probe.g * 255), b: Math.round(probe.b * 255) }
    }

    function cleanup() {
        Theme.palette = "day"
    }

    // Night vision: reds and black only, no channel other than red above 0x20 in any night colour.
    function test_nightIsRedAndBlackOnly() {
        const keys = Object.keys(Theme.night)
        verify(keys.length >= 10, "night has " + keys.length + " colours")
        for (const k of keys) {
            const c = channels(Theme.night[k])
            verify(c.g <= 0x20 && c.b <= 0x20, k + " is " + Theme.night[k])
        }
    }

    function test_nightBackgroundIsBlack() {
        compare(channels(Theme.night.background), { r: 0, g: 0, b: 0 })
    }

    function test_palettesHaveTheSameColours() {
        const keys = Object.keys(Theme.day).sort()
        compare(Object.keys(Theme.dusk).sort(), keys)
        compare(Object.keys(Theme.night).sort(), keys)
    }

    function test_paletteSwitchesTheColours_data() {
        return [{ tag: "day" }, { tag: "dusk" }, { tag: "night" }]
    }
    function test_paletteSwitchesTheColours(data) {
        Theme.palette = data.tag
        const set = Theme[data.tag]
        for (const k of Object.keys(set)) {
            verify(Theme[k] !== undefined, "Theme." + k + " missing")
            probe = set[k]
            compare(Theme[k], probe, k)
        }
    }

    function test_unknownPaletteIsDay() {
        Theme.palette = "noon"
        probe = Theme.day.text
        compare(Theme.text, probe)
    }

    function test_everyIconLoads() {
        const names = Icons.names()
        compare(names.length, 16)
        for (const n of names) {
            const icon = createTemporaryObject(iconComp, testCase, { name: n, width: Units.mm(10), height: Units.mm(10) })
            tryCompare(icon, "status", Image.Ready, 5000, n)
        }
    }

    // At night an icon in the button text colour is red on black: no green or blue above 0x20.
    function test_iconIsRedAtNight() {
        Theme.palette = "night"
        const box = createTemporaryObject(iconBoxComp, testCase, { width: Units.mm(20), height: Units.mm(20) })
        box.icon.name = "anchor"
        box.icon.width = Units.mm(12)
        box.icon.height = Units.mm(12)
        tryCompare(box.icon, "status", Image.Ready)
        const img = grabImage(box)
        let red = 0, bad = 0
        for (let y = 0; y < img.height; ++y) {
            for (let x = 0; x < img.width; ++x) {
                if (img.green(x, y) > 0x20 || img.blue(x, y) > 0x20) ++bad
                if (img.red(x, y) > 0x80) ++red
            }
        }
        verify(bad === 0, bad + " pixels have green or blue above 0x20")
        verify(red > 0, "the icon drew red pixels")
    }

    // A half-transparent colour draws half-strength pixels, not opaque ones.
    function test_iconColorAlpha() {
        const box = createTemporaryObject(iconBoxComp, testCase, { width: Units.mm(20), height: Units.mm(20) })
        box.icon.name = "anchor"
        box.icon.width = Units.mm(12)
        box.icon.height = Units.mm(12)
        box.icon.color = Qt.rgba(1, 0, 0, 0.5)
        tryCompare(box.icon, "status", Image.Ready)
        const img = grabImage(box)
        let peak = 0
        for (let y = 0; y < img.height; ++y)
            for (let x = 0; x < img.width; ++x)
                peak = Math.max(peak, img.red(x, y))
        verify(peak > 0x40 && peak < 0xc0, "peak red is " + peak)
    }

    function test_unknownIconWarns() {
        ignoreWarning(new RegExp("unknown icon"))
        const icon = createTemporaryObject(iconComp, testCase, { name: "nope", width: 20, height: 20 })
        compare(icon.source.toString(), "")
    }
}
