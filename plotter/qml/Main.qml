import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import CheekyMarine as CM

// The app shell: the no-data banner over the pages, the tab bar on the right edge, the boot splash.
ApplicationWindow {
    id: root
    required property QtObject chart              // ChartController
    required property Item chartMap               // MapLibreChartMap
    required property QtObject paletteController  // PaletteController
    required property QtObject settings           // Settings
    required property QtObject vessel             // VesselModel
    required property QtObject appInfo            // AppInfo
    required property var slotsModel              // SlotsModel
    required property var numbersModel            // NumbersModel
    required property QtObject touchLock          // TouchLock
    required property QtObject tracksController   // TracksController
    // chart, numbers, tracks, settings or about
    property string page: "chart"

    width: 1024
    height: 600
    visible: true
    title: "CheekyMarine"
    color: Theme.background
    font.family: Units.fontFamily

    Binding { target: Theme; property: "palette"; value: root.paletteController.palette }
    Binding { target: Units; property: "windowWidth"; value: root.width }
    Binding { target: Units; property: "windowHeight"; value: root.height }
    Binding { target: Units; property: "diagonalIn"; value: root.settings.panelDiagonalIn }

    readonly property var pages: ["chart", "numbers", "tracks", "settings", "about"]

    RowLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            NoDataBanner {
                Layout.fillWidth: true
                live: root.vessel.live
                schemaMismatch: root.appInfo.schemaMismatch
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: Math.max(0, root.pages.indexOf(root.page))

                ChartPage {
                    id: chartPage
                    chart: root.chart
                    chartMap: root.chartMap
                    slotsModel: root.slotsModel
                }
                NumbersPage {
                    model: root.numbersModel
                }
                TracksPage {
                    tracks: root.tracksController
                    settings: root.settings
                }
                SettingsPage {
                    settings: root.settings
                    onEditOverlays: {
                        chartPage.editing = true
                        root.page = "chart"
                    }
                    onShowAbout: root.page = "about"
                }
                AboutPage {
                    appInfo: root.appInfo
                    onBack: root.page = "settings"
                }
            }
        }

        CM.TabBar { // ours, not the Controls TabBar
            id: tabBar
            opacity: root.touchLock.locked ? 0.45 : 1
            Layout.fillHeight: true
            current: root.page === "about" ? "settings" : root.page
            paletteMode: root.settings.paletteMode
            recording: root.settings.trackRecording
            onPageSelected: (p) => root.page = p
            onLockRequested: root.touchLock.lockNow()
            onPaletteCycled: {
                const modes = ["auto", "day", "dusk", "night"]
                root.settings.paletteMode = modes[(modes.indexOf(root.settings.paletteMode) + 1) % modes.length]
            }
        }
    }

    LockOverlay {
        anchors.fill: parent
        lock: root.touchLock
        anchorItem: tabBar.lockButton
    }

    Splash {
        anchors.fill: parent
        appInfo: root.appInfo
    }
}
