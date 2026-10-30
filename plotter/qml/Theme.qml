pragma Singleton
import QtQuick

// UI colours for the day, dusk and night palettes. `palette` follows PaletteController (Main.qml
// binds it); the flat properties are the current palette's colours. Night keeps night vision: reds
// and black only, no channel other than red above 0x20 (tests/qml/tst_theme.qml checks it).
QtObject {
    property string palette: "day"

    readonly property var day: ({
        background: "#f2f2f2",
        text: "#000000",
        button: "#ffffff",
        buttonDown: "#c8c8c8",
        buttonText: "#000000",
        buttonBorder: "#505050",
        disabledButton: "#e4e4e4",
        disabledText: "#808080",
        noticeBackground: "#c0ffffff",
        noticeText: "#000000",
        alertBackground: "#c62828",
        alertText: "#ffffff"
    })
    readonly property var dusk: ({
        background: "#303036",
        text: "#e0e0e0",
        button: "#3a3a42",
        buttonDown: "#55555f",
        buttonText: "#f0f0f0",
        buttonBorder: "#8a8a94",
        disabledButton: "#2c2c32",
        disabledText: "#8a8a8a",
        noticeBackground: "#c0202024",
        noticeText: "#d8d8d8",
        alertBackground: "#a51c1c",
        alertText: "#ffffff"
    })
    readonly property var night: ({
        background: "#000000",
        text: "#c00000",
        button: "#1a0000",
        buttonDown: "#400000",
        buttonText: "#e00000",
        buttonBorder: "#800000",
        disabledButton: "#0c0000",
        disabledText: "#600000",
        noticeBackground: "#c0000000",
        noticeText: "#a00000",
        alertBackground: "#500000",
        alertText: "#ff2020"
    })

    readonly property var current: palette === "night" ? night : palette === "dusk" ? dusk : day

    readonly property color background: current.background
    readonly property color text: current.text
    readonly property color button: current.button
    readonly property color buttonDown: current.buttonDown
    readonly property color buttonText: current.buttonText
    readonly property color buttonBorder: current.buttonBorder
    readonly property color disabledButton: current.disabledButton
    readonly property color disabledText: current.disabledText
    readonly property color noticeBackground: current.noticeBackground
    readonly property color noticeText: current.noticeText
    readonly property color alertBackground: current.alertBackground
    readonly property color alertText: current.alertText
}
