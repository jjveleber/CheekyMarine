// QuickTest runner for every tests/qml/tst_*.qml. The CheekyMarine QML module is linked in statically.
#include <QtQml/qqmlextensionplugin.h>
#include <QtQuickTest>

Q_IMPORT_QML_PLUGIN(CheekyMarinePlugin)

QUICK_TEST_MAIN(cheekymarine_qml)
