pragma Singleton
import QtQuick
import CheekyMarine

// Physical sizes. Main.qml binds the window size and the panel diagonal setting; every size in the
// UI is mm(x). A slot's digit height in mm makes a "8" that tall: the font pixel size is calibrated
// from the bold font's tight bounding box of "8".
QtObject {
    id: units

    property int windowWidth: 1024
    property int windowHeight: 600
    property real diagonalIn: 10.1
    readonly property real pxPerMm: PanelMath.pxPerMm(windowWidth, windowHeight, diagonalIn)
    function mm(x) { return x * pxPerMm }

    // Noto Sans, bundled, so the panel and the dev desktop draw the same glyphs.
    readonly property FontLoader regularFont: FontLoader { source: "../fonts/NotoSans-Regular.ttf" }
    readonly property FontLoader boldFont: FontLoader { source: "../fonts/NotoSans-Bold.ttf" }
    readonly property string fontFamily: regularFont.name
    readonly property bool fontsReady: regularFont.status === FontLoader.Ready && boldFont.status === FontLoader.Ready

    readonly property FontMetrics digitMetrics: FontMetrics {
        font.family: units.fontFamily
        font.bold: true
        font.pixelSize: 200
    }
    // Height of "8" as a fraction of the pixel size (about 0.71 for Noto Sans Bold). Measured only
    // once both fonts are loaded: before that it would be a fallback face or a synthesized bold.
    readonly property real digitRatio: {
        // tightBoundingRect() is a call, so it adds no binding dependency on the font: reading the
        // family (and fontsReady) here is what re-evaluates this when the fonts arrive.
        const family = digitMetrics.font.family
        if (!fontsReady || family === "") return 0.714
        const r = digitMetrics.tightBoundingRect("8").height / 200
        return r > 0.3 ? r : 0.714
    }
    // Font pixel size whose "8" is heightMm tall.
    function digitPixelSize(heightMm) { return Math.ceil(mm(heightMm) / digitRatio) }
    // Width of `text` in the bold digit face per mm of digit height; a two-line text takes its wider
    // line. Like digitRatio it is measured on the loaded fonts: a binding calling this reads
    // fontsReady, the family and digitRatio, so it re-evaluates when the fonts arrive.
    function textWidthPerDigitMm(text) {
        void fontsReady, digitMetrics.font.family // advanceWidth() is a call: these are the dependencies
        let widest = 0
        for (const line of text.split("\n")) widest = Math.max(widest, digitMetrics.advanceWidth(line))
        return widest / (200 * digitRatio)
    }
}
