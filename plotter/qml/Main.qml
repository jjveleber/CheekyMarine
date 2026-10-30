import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: root
    required property QtObject chart   // ChartController
    required property Item chartMap    // MapLibreChartMap

    width: 1024
    height: 600
    visible: true
    title: "CheekyMarine"

    ChartPage {
        anchors.fill: parent
        chart: root.chart
        chartMap: root.chartMap
    }
}
