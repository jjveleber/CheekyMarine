import QtQuick
import QtQuick.Controls.Basic

ApplicationWindow {
    id: root
    required property QtObject chart              // ChartController
    required property Item chartMap               // MapLibreChartMap
    required property QtObject paletteController  // PaletteController

    width: 1024
    height: 600
    visible: true
    title: "CheekyMarine"
    color: Theme.background

    Binding {
        target: Theme
        property: "palette"
        value: root.paletteController.palette
    }

    ChartPage {
        anchors.fill: parent
        chart: root.chart
        chartMap: root.chartMap
    }
}
