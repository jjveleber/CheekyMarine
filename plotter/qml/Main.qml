import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import CheekyMarine as CM

// The app shell: the no-data banner over the pages, the tab bar over their right edge, the boot
// splash. Pages: Home (the tiles), the shown view (chart or cells), Tracks, Settings, About.
ApplicationWindow {
    id: root
    required property QtObject chart              // ChartController
    required property Item chartMap               // MapLibreChartMap
    required property QtObject paletteController  // PaletteController
    required property QtObject settings           // Settings
    required property QtObject vessel             // VesselModel
    required property QtObject appInfo            // AppInfo
    required property QtObject views              // ViewsModel
    required property QtObject draft              // ViewDraft: the shown view
    required property QtObject touchLock          // TouchLock
    required property QtObject tracksController   // TracksController
    // home, view (the shown view), tracks, settings or about
    property string page: "view"
    property bool legendOpen: false // dev option --sheet legend
    property bool editing: false    // the view editor is open (Task 9)
    // On a view the bar slides off after this delay (0: never); tests set it shorter.
    property int hideDelayMs: root.settings.tabBarHideS * 1000

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
    // As many favourite tabs as the bar's column holds.
    Binding { target: root.views; property: "favouriteCapacity"; value: PanelMath.favouriteCapacity(tabBar.height / Units.pxPerMm) }

    readonly property var pages: ["home", "view", "tracks", "settings", "about"]

    // The current view into the draft; its chart picks the chart mode.
    function showCurrentView() {
        root.draft.loadJson(root.views.viewJson(root.views.currentId))
        root.chart.mode = root.draft.chart === "fish" ? "fish" : "nav"
    }
    // A new current id loads the draft (onCurrentIdChanged below); the shown view stays loaded.
    function showView(id) {
        root.views.currentId = id
        root.page = "view"
    }
    // The view editor arrives with Task 9.
    function editView(id) {}
    function newView() {
        root.showView(root.views.add())
    }
    Component.onCompleted: showCurrentView()
    Connections {
        target: root.views
        function onCurrentIdChanged() { root.showCurrentView() }
    }

    // The bar back for the full delay. Restarted only while it runs: the binding starts it.
    function showBar() {
        tabBar.shown = true
        if (hideTimer.running) hideTimer.restart()
    }
    onPageChanged: showBar()
    // Not while locked: the unlock hold is over the bar's Lock button.
    Timer {
        id: hideTimer
        interval: root.hideDelayMs
        running: root.page === "view" && !root.editing && root.hideDelayMs > 0 && tabBar.shown && !root.touchLock.locked
        onTriggered: tabBar.shown = false
    }
    Connections {
        target: root.touchLock
        function onLockedChanged() { if (root.touchLock.locked) root.showBar() }
    }

    // The pages fill the window; the tab bar lies over their right edge (rightInset).
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        NoDataBanner {
            Layout.fillWidth: true
            Layout.rightMargin: tabBar.width
            live: root.vessel.live
            schemaMismatch: root.appInfo.schemaMismatch
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: Math.max(0, root.pages.indexOf(root.page))

            HomePage {
                views: root.views
                rightInset: tabBar.width
                onViewSelected: (id) => root.showView(id)
                onEditView: (id) => root.editView(id)
                onNewView: root.newView()
                onShowTracks: root.page = "tracks"
                onShowSettings: root.page = "settings"
                onShowAbout: root.page = "about"
            }
            // A view with a chart shows the chart page, one without the cell page.
            Item {
                ChartPage {
                    anchors.fill: parent
                    visible: root.draft.chart !== "none"
                    chart: root.chart
                    chartMap: root.chartMap
                    draft: root.draft
                    rightInset: tabBar.width
                    onPlainTap: root.showBar()
                    Component.onCompleted: if (root.legendOpen) openLegend()
                }
                CellPage {
                    anchors.fill: parent
                    visible: root.draft.chart === "none"
                    draft: root.draft
                    rightInset: tabBar.width
                    onPlainTap: root.showBar()
                }
            }
            TracksPage {
                tracks: root.tracksController
                settings: root.settings
                rightInset: tabBar.width
            }
            SettingsPage {
                settings: root.settings
                rightInset: tabBar.width
                onShowAbout: root.page = "about"
            }
            AboutPage {
                appInfo: root.appInfo
                rightInset: tabBar.width
                onBack: root.page = "home"
            }
        }
    }

    // On top of the pages at the right edge; slides off it when not shown.
    CM.TabBar { // ours, not the Controls TabBar
        id: tabBar
        anchors { top: parent.top; bottom: parent.bottom }
        width: implicitWidth
        x: tabBar.shown ? root.width - tabBar.width : root.width
        opacity: root.touchLock.locked ? 0.45 : 1
        tabViews: root.views.tabViews
        currentId: root.page === "view" ? root.views.currentId : ""
        homeHighlighted: {
            void root.views.tabViews // onTabBar() is a call: tabViews changes whenever its answer can
            return root.page === "home" || (root.page === "view" && !root.views.onTabBar(root.views.currentId))
        }
        paletteMode: root.settings.paletteMode
        recording: root.settings.trackRecording
        onViewSelected: (id) => root.showView(id)
        onHomeSelected: root.page = "home"
        onTouched: root.showBar()
        onLockRequested: { root.showBar(); root.touchLock.lockNow() }
        onPaletteCycled: {
            const modes = ["auto", "day", "dusk", "night"]
            root.settings.paletteMode = modes[(modes.indexOf(root.settings.paletteMode) + 1) % modes.length]
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
