import QtQuick
import CheekyMarine

// A bundled Tabler icon drawn in `color` (the button text colour by default, so it follows the palette).
Image {
    property string name
    property color color: Theme.buttonText
    source: Icons.source(name, color)
    sourceSize: Qt.size(width, height)
    fillMode: Image.PreserveAspectFit
}
