#include "core/Settings.h"
#include "core/Store.h"
#include <QSignalSpy>
#include <QSqlQuery>
#include <QTemporaryDir>
#include <QtTest>

namespace {
void rawSql(Store& s, const QString& sql) {
    QSqlQuery q(s.db());
    QVERIFY2(q.exec(sql), qPrintable(sql));
}
QString rawValue(Store& s, const QString& key) {
    QSqlQuery q(s.db());
    q.prepare("SELECT value FROM settings WHERE key=?");
    q.addBindValue(key);
    return q.exec() && q.next() ? q.value(0).toString() : QString();
}
} // namespace

class TstSettings : public QObject {
    Q_OBJECT
private slots:
    void defaultsWhenEmpty() {
        QTemporaryDir t;
        auto st = Store::open(t.path());
        QVERIFY(st.has_value());
        Settings s(**st);
        QCOMPARE(s.depthUnit(), QStringLiteral("ft"));
        QCOMPARE(s.speedUnit(), QStringLiteral("kn"));
        QCOMPARE(s.tempUnit(), QStringLiteral("F"));
        QVERIFY(s.applyDepthOffset());
        QCOMPARE(s.shallowM(), 1.8288);
        QCOMPARE(s.safetyM(), 3.048);
        QCOMPARE(s.deepM(), 9.144);
        QCOMPARE(s.orientation(), QStringLiteral("head"));
        QCOMPARE(s.paletteMode(), QStringLiteral("auto"));
        QCOMPARE(s.lastPalette(), QStringLiteral("day"));
        QCOMPARE(s.chartMode(), QStringLiteral("nav"));
        QCOMPARE(s.touchLockTimeoutS(), 120);
        QCOMPARE(s.panelDiagonalIn(), 10.1);
        QVERIFY(!s.trackRecording());
        QCOMPARE(s.trackIntervalS(), 5);
        QCOMPARE(s.trackMinDistanceM(), 10.0);
        QVERIFY(s.slotsJson().toArray().isEmpty());
        QCOMPARE(s.bigNumbers(), (QStringList{"depth", "sog"}));
        const UnitPrefs p = s.unitPrefs();
        QCOMPARE(p.depth, DepthUnit::Feet);
        QCOMPARE(p.speed, SpeedUnit::Knots);
        QCOMPARE(p.temp, TempUnit::F);
        QVERIFY(p.applyDepthOffset);
    }
    void setThenReopenKeepsValue() {
        QTemporaryDir t;
        {
            auto st = Store::open(t.path());
            Settings s(**st);
            QSignalSpy spy(&s, &Settings::orientationChanged);
            s.setOrientation("north");
            s.setOrientation("north"); // unchanged: no second notify
            QCOMPARE(spy.count(), 1);
            s.setDepthUnit("m");
            s.setSpeedUnit("kmh");
            s.setTempUnit("C");
            s.setApplyDepthOffset(false);
            s.setBigNumbers({"depth", "stw", "cog"});
            s.setTouchLockTimeoutS(0);
            s.setTrackRecording(true);
            QTest::ignoreMessage(QtWarningMsg, QRegularExpression("paletteMode"));
            s.setPaletteMode("bogus"); // rejected
            QCOMPARE(s.paletteMode(), QStringLiteral("auto"));
            QTest::ignoreMessage(QtWarningMsg, QRegularExpression("chartMode"));
            s.setChartMode("bogus"); // rejected: only nav and fish are stored
            QCOMPARE(s.chartMode(), QStringLiteral("nav"));
            s.setChartMode("fish");
            QCOMPARE(s.chartMode(), QStringLiteral("fish"));
            QSignalSpy lastSpy(&s, &Settings::lastPaletteChanged);
            s.setLastPalette("night");
            QCOMPARE(lastSpy.count(), 1);
            QTest::ignoreMessage(QtWarningMsg, QRegularExpression("lastPalette"));
            s.setLastPalette("auto"); // rejected: only an applied palette is stored
            QCOMPARE(s.lastPalette(), QStringLiteral("night"));
        }
        auto st = Store::open(t.path());
        Settings s(**st);
        QCOMPARE(s.orientation(), QStringLiteral("north"));
        QCOMPARE(s.bigNumbers(), (QStringList{"depth", "stw", "cog"}));
        QCOMPARE(s.touchLockTimeoutS(), 0);
        QCOMPARE(s.lastPalette(), QStringLiteral("night"));
        QVERIFY(s.trackRecording());
        const UnitPrefs p = s.unitPrefs();
        QCOMPARE(p.depth, DepthUnit::Metres);
        QCOMPARE(p.speed, SpeedUnit::Kmh);
        QCOMPARE(p.temp, TempUnit::C);
        QVERIFY(!p.applyDepthOffset);
    }
    void unitStringMapping() {
        QTemporaryDir t;
        auto st = Store::open(t.path());
        Settings s(**st);
        s.setDepthUnit("fm");
        s.setSpeedUnit("mph");
        QCOMPARE(s.unitPrefs().depth, DepthUnit::Fathoms);
        QCOMPARE(s.unitPrefs().speed, SpeedUnit::Mph);
    }
    void unknownKeySurvivesSave() {
        QTemporaryDir t;
        {
            auto st = Store::open(t.path());
            rawSql(**st, R"(INSERT INTO settings VALUES('futureKey','{"a":[1,2]}'))");
            Settings s(**st);
            s.setOrientation("course");
            QVERIFY(s.setDepths(1.5, 3.5, 10));
        }
        auto st = Store::open(t.path());
        QCOMPARE(rawValue(**st, "futureKey"), QStringLiteral(R"({"a":[1,2]})"));
        Settings s(**st);
        QCOMPARE(s.orientation(), QStringLiteral("course"));
    }
    void unparseableValueFallsBackToDefault() {
        QTemporaryDir t;
        auto st = Store::open(t.path());
        rawSql(**st, "INSERT INTO settings VALUES('speedUnit','{not json')");
        rawSql(**st, "INSERT INTO settings VALUES('orientation','\"sideways\"')"); // parses, not allowed
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("speedUnit"));
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression("orientation"));
        Settings s(**st);
        QCOMPARE(s.speedUnit(), QStringLiteral("kn"));
        QCOMPARE(s.orientation(), QStringLiteral("head"));
    }
    void invalidDepthsRejected_data() {
        QTest::addColumn<double>("a");
        QTest::addColumn<double>("b");
        QTest::addColumn<double>("c");
        QTest::newRow("descending") << 3.0 << 2.0 << 9.0;
        QTest::newRow("equal") << 1.0 << 1.0 << 9.0;
        QTest::newRow("below range") << 0.4 << 3.0 << 9.0;
        QTest::newRow("above range") << 1.0 << 3.0 << 61.0;
    }
    void invalidDepthsRejected() {
        QFETCH(double, a);
        QFETCH(double, b);
        QFETCH(double, c);
        QTemporaryDir t;
        auto st = Store::open(t.path());
        Settings s(**st);
        QSignalSpy sp1(&s, &Settings::shallowMChanged), sp2(&s, &Settings::safetyMChanged), sp3(&s, &Settings::deepMChanged);
        QVERIFY(!s.setDepths(a, b, c));
        QVERIFY(!Settings::depthsProblem(a, b, c).isEmpty());
        QCOMPARE(s.shallowM(), 1.8288);
        QCOMPARE(s.safetyM(), 3.048);
        QCOMPARE(s.deepM(), 9.144);
        QCOMPARE(sp1.count() + sp2.count() + sp3.count(), 0);
        QCOMPARE(rawValue(**st, "shallowM"), QString());
    }
    // A code and, for a range problem, the limit in metres: the page words it in the user's unit.
    void depthsProblemGivesCodeAndLimit_data() {
        QTest::addColumn<double>("a");
        QTest::addColumn<double>("b");
        QTest::addColumn<double>("c");
        QTest::addColumn<QString>("code");
        QTest::addColumn<double>("limitM");
        QTest::newRow("ok") << 0.5 << 1.0 << 60.0 << QString() << -1.0;
        QTest::newRow("below range") << 0.4 << 3.0 << 9.0 << "belowMin" << 0.5;
        QTest::newRow("above range") << 1.0 << 3.0 << 61.0 << "aboveMax" << 60.0;
        QTest::newRow("shallow not below safety") << 3.0 << 3.0 << 9.0 << "shallowSafety" << -1.0;
        QTest::newRow("safety not below deep") << 1.0 << 9.0 << 9.0 << "safetyDeep" << -1.0;
    }
    void depthsProblemGivesCodeAndLimit() {
        QFETCH(double, a);
        QFETCH(double, b);
        QFETCH(double, c);
        QFETCH(QString, code);
        QFETCH(double, limitM);
        const QVariantMap p = Settings::depthsProblem(a, b, c);
        if (code.isEmpty()) {
            QVERIFY(p.isEmpty());
            return;
        }
        QCOMPARE(p.value("code").toString(), code);
        QCOMPARE(p.contains("limitM"), limitM >= 0);
        if (limitM >= 0) QCOMPARE(p.value("limitM").toDouble(), limitM);
    }
    void depthBoundsAreInclusive() {
        QTemporaryDir t;
        auto st = Store::open(t.path());
        Settings s(**st);
        QVERIFY(s.setDepths(0.5, 1.0, 60.0));
        QCOMPARE(s.shallowM(), 0.5);
        QCOMPARE(s.deepM(), 60.0);
    }
    void validDepthsEmitEachChangeOnce() {
        QTemporaryDir t;
        auto st = Store::open(t.path());
        Settings s(**st);
        QSignalSpy sp1(&s, &Settings::shallowMChanged), sp2(&s, &Settings::safetyMChanged), sp3(&s, &Settings::deepMChanged);
        QVERIFY(s.setDepths(1.5, 3.5, 10));
        QCOMPARE(sp1.count(), 1);
        QCOMPARE(sp2.count(), 1);
        QCOMPARE(sp3.count(), 1);
        QVERIFY(s.setDepths(1.5, 3.5, 12)); // only deep changes
        QCOMPARE(sp1.count(), 1);
        QCOMPARE(sp2.count(), 1);
        QCOMPARE(sp3.count(), 2);
        QCOMPARE(s.deepM(), 12.0);
    }
};

QTEST_GUILESS_MAIN(TstSettings)
#include "tst_settings.moc"
