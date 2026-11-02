#include <QtTest>

#include "plotter/Version.h"

class TstVersion : public QObject {
    Q_OBJECT
private slots:
    void versionMatchesCMake() { QCOMPARE(QString(kPlotterVersion), QString(PLOTTER_EXPECTED_VERSION)); }
};

QTEST_GUILESS_MAIN(TstVersion)
#include "tst_version.moc"
