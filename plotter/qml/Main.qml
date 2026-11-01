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
    property bool editing: false    // the view editor is open
    property string editorFrom: "view" // the page the editor returns to on Cancel
    property bool editingNew: false // the edited view was just added
    property bool setupRequestedOnOpen: false // the editor was asked to open its Setup sheet first
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
        editor.closeSheets()
        root.draft.loadJson(root.views.viewJson(root.views.currentId))
        root.chart.mode = root.draft.chart === "fish" ? "fish" : "nav"
    }
    // A new current id loads the draft (onCurrentIdChanged below); the shown view stays loaded.
    function showView(id) {
        root.views.currentId = id
        root.page = "view"
    }
    // The editor over the view `id`; the bar stays shown, dimmed and inert, until Done or Cancel.
    function editView(id, openSetup) {
        root.editorFrom = root.page
        root.setupRequestedOnOpen = openSetup === true
        root.showView(id)
        root.editing = true
        root.showBar()
    }
    function newView() {
        const id = root.views.add()
        root.editingNew = true
        root.editView(id, true)
    }
    function editorDone() {
        root.views.saveJson(root.draft.toJson())
        root.editing = false
        root.editingNew = false
        root.page = "view"
    }
    // Every change since the editor opened is dropped; a view added for it goes again.
    function editorCancel() {
        const id = root.draft.id
        root.editing = false
        if (root.editingNew) {
            root.editingNew = false
            root.views.remove(id)
            root.page = "home"
        } else {
            root.showCurrentView()
            root.page = root.editorFrom
        }
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
    onPageChanged: {
        showBar()
        // A sheet opened by a hold on a live view, left without its Done, keeps nothing.
        if (editor.sheetOpen && !root.editing) root.showCurrentView()
    }
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
                    id: chartPage
                    anchors.fill: parent
                    visible: root.draft.chart !== "none"
                    chart: root.chart
                    chartMap: root.chartMap
                    draft: root.draft
                    rightInset: tabBar.width
                    editing: root.editing
                    selectedSlot: root.editing ? editor.selectedSlot : ""
                    onPlainTap: root.showBar()
                    onSlotTapped: (id) => editor.openSlotSheet(id)
                    onSlotHeld: (id) => editor.openSlotSheet(id)
                    onHandleDragged: (id, innerX, innerY) => editor.dragSlot(id, innerX, innerY)
                    Component.onCompleted: if (root.legendOpen) openLegend()
                }
                CellPage {
                    id: cellPage
                    anchors.fill: parent
                    visible: root.draft.chart === "none"
                    draft: root.draft
                    rightInset: tabBar.width
                    editing: root.editing
                    onPlainTap: root.showBar()
                    onCellTapped: (index) => editor.openCellSheet(index)
                    onCellHeld: (index) => editor.openCellSheet(index)
                }
                ViewEditor {
                    id: editor
                    anchors.fill: parent
                    draft: root.draft
                    rightInset: tabBar.width
                    editing: root.editing
                    chartPage: chartPage
                    cellPage: cellPage
                    onDoneRequested: root.editorDone()
                    onCancelRequested: root.editorCancel()
                    // A hold's sheet on a live view saves on its Done.
                    onSheetClosed: if (!root.editing) root.views.saveJson(root.draft.toJson())
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
        enabled: !root.editing
        opacity: root.touchLock.locked || root.editing ? 0.45 : 1
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

    // The editor's dimmed bar is disabled, so presses would fall through to the map under the
    // strip: this takes them and does nothing.
    MouseArea {
        objectName: "inertBarCover"
        x: tabBar.x
        width: tabBar.width
        height: root.height
        enabled: root.editing
        visible: root.editing
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
