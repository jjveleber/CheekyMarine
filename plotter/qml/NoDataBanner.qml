import QtQuick
import QtQuick.Controls.Basic

// Full-width banner while there is no live data: "No data from N2K", or "Daemon too new or too
// old" once n2kd's hello carried a schema this app does not speak.
Rectangle {
    id: banner
    property bool live: false
    property bool schemaMismatch: false
    readonly property string text: schemaMismatch ? "Daemon too new or too old" : "No data from N2K"

    objectName: "noDataBanner"
    visible: !live
    implicitHeight: Units.mm(10)
    color: Theme.alertBackground

    Label {
        anchors.centerIn: parent
        text: banner.text
        color: Theme.alertText
        font.pixelSize: Units.mm(5)
        font.bold: true
    }
}
