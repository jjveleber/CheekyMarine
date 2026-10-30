import QtQuick
import QtTest
import CheekyMarine

TestCase {
    name: "Theme"

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
}
