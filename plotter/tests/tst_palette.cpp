#include "app/Icons.h"
#include "core/Overlays.h"
#include "core/PaletteController.h"
#include "core/Settings.h"
#include "core/Store.h"
#include "core/Sun.h"
#include "core/VesselModel.h"
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTimer>
#include <QtTest>
#include <memory>

namespace {
constexpr double kSeattleLat = 47.6062, kSeattleLon = -122.3321;

QDateTime utc(const char* iso) { return QDateTime::fromString(QString::fromLatin1(iso), Qt::ISODate); }

VesselState seattleAt(const QDateTime& t) {
    VesselState v;
    v.lat = kSeattleLat;
    v.lon = kSeattleLon;
    v.gnssTime = double(t.toSecsSinceEpoch());
    return v;
}

// Night vision rule shared with Theme.qml: nothing but red above 0x20.
bool nightSafe(const QColor& c) { return c.green() <= 0x20 && c.blue() <= 0x20; }

struct Rig {
    QTemporaryDir tmp;
    std::unique_ptr<Store> store;
    std::unique_ptr<Settings> settings;
    VesselModel vessel;
    QDateTime now = utc("2026-06-21T20:00:00Z"); // midday in Seattle
    std::unique_ptr<PaletteController> ctrl;

    Rig() {
        auto st = Store::open(tmp.path());
        if (!st) return;
        store = std::move(*st);
        settings = std::make_unique<Settings>(*store);
        vessel.setLive(true);
    }
    PaletteController& make() {
        ctrl = std::make_unique<PaletteController>(*settings, vessel, [this] { return now; });
        return *ctrl;
    }
};
} // namespace

class TstPalette : public QObject {
    Q_OBJECT
private slots:
    // Seattle, 2026-06-21 (USNO: begin civil 11:31, rise 12:12, set 04:11, end civil 04:51).
    void paletteAtSeattleJune_data() {
        QTest::addColumn<QString>("when");
        QTest::addColumn<QString>("want");
        QTest::newRow("12:00 civil twilight") << "2026-06-21T12:00:00Z" << "dusk";
        QTest::newRow("12:30 after sunrise") << "2026-06-21T12:30:00Z" << "day";
        QTest::newRow("04:00 before sunset") << "2026-06-21T04:00:00Z" << "day";
        QTest::newRow("04:30 after sunset") << "2026-06-21T04:30:00Z" << "dusk";
        QTest::newRow("05:00 after civil dusk") << "2026-06-21T05:00:00Z" << "night";
    }
    void paletteAtSeattleJune() {
        QFETCH(QString, when);
        QFETCH(QString, want);
        const QDateTime t = QDateTime::fromString(when, Qt::ISODate);
        QCOMPARE(paletteName(paletteAt(t, kSeattleLat, kSeattleLon)), want);
    }

    // The controller in auto mode gives the same answers from the vessel's position and GNSS time.
    void autoUsesVesselPositionAndGnssTime_data() { paletteAtSeattleJune_data(); }
    void autoUsesVesselPositionAndGnssTime() {
        QFETCH(QString, when);
        QFETCH(QString, want);
        Rig r;
        QVERIFY(r.settings);
        QCOMPARE(r.settings->paletteMode(), QStringLiteral("auto"));
        r.make();
        r.vessel.setState(seattleAt(QDateTime::fromString(when, Qt::ISODate)));
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), want);
    }

    void autoWithoutGnssTimeUsesNow() {
        Rig r;
        QVERIFY(r.settings);
        r.now = utc("2026-06-21T05:00:00Z");
        r.make();
        VesselState v = seattleAt(r.now);
        v.gnssTime.reset();
        r.vessel.setState(v);
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("night"));
    }

    void manualNightRegardless() {
        Rig r;
        QVERIFY(r.settings);
        r.settings->setPaletteMode("night");
        r.make();
        r.vessel.setState(seattleAt(utc("2026-06-21T20:00:00Z"))); // broad daylight
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("night"));
        r.vessel.setLive(false); // no position at all
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("night"));
    }

    void manualDayAndDusk() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.vessel.setState(seattleAt(utc("2026-06-21T05:00:00Z"))); // night
        r.settings->setPaletteMode("dusk");
        QCOMPARE(r.ctrl->palette(), QStringLiteral("dusk")); // a mode change applies at once
        r.settings->setPaletteMode("day");
        QCOMPARE(r.ctrl->palette(), QStringLiteral("day"));
        r.settings->setPaletteMode("auto");
        QCOMPARE(r.ctrl->palette(), QStringLiteral("night"));
    }

    void autoWithoutPositionKeepsPrevious() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("day")); // initially day
        r.vessel.setState(seattleAt(utc("2026-06-21T04:30:00Z")));
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("dusk"));
        r.now = utc("2026-06-21T05:00:00Z"); // would be night, but there is no position
        r.vessel.setLive(false);
        r.ctrl->evaluate();
        QCOMPARE(r.ctrl->palette(), QStringLiteral("dusk"));
    }

    // Startup has no position; the first fix decides at once rather than up to a minute later.
    void firstPositionEvaluatesAtOnce() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        QSignalSpy spy(r.ctrl.get(), &PaletteController::paletteChanged);
        r.vessel.setState(seattleAt(utc("2026-06-21T05:00:00Z")));
        QCOMPARE(r.ctrl->palette(), QStringLiteral("night"));
        QCOMPARE(spy.count(), 1);
        r.vessel.setState(seattleAt(utc("2026-06-21T05:00:30Z"))); // no change, no signal
        QCOMPARE(spy.count(), 1);
    }

    void evaluatesEveryMinute() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        const auto timers = r.ctrl->findChildren<QTimer*>();
        QCOMPARE(timers.size(), 1);
        QCOMPARE(timers[0]->interval(), 60000);
        QVERIFY(timers[0]->isActive());
        QVERIFY(!timers[0]->isSingleShot());
    }

    void nightOverlayColoursAreRedOnly() {
        const OverlayColours c = overlayColours(QStringLiteral("night"));
        for (const QColor& col : {c.boatFill, c.boatOutline, c.aisFill, c.aisOutline, c.heading, c.cog, c.aisVector,
                                  c.track})
            QVERIFY2(nightSafe(col), qPrintable(col.name(QColor::HexArgb)));
    }

    void overlayColoursDifferPerPalette() {
        QVERIFY(overlayColours("day").boatFill != overlayColours("night").boatFill);
        QVERIFY(overlayColours("dusk").heading != overlayColours("night").heading);
    }

    // Every pixel of every night icon obeys the rule; the boat is drawn in the palette's colours.
    void nightIconsAreRedOnly() {
        const auto icons = chartIcons(4.0, QStringLiteral("night"));
        QCOMPARE(icons.size(), 4);
        for (auto it = icons.cbegin(); it != icons.cend(); ++it) {
            const QImage img = it.value().convertToFormat(QImage::Format_ARGB32);
            int opaque = 0;
            for (int y = 0; y < img.height(); ++y)
                for (int x = 0; x < img.width(); ++x) {
                    const QColor px = img.pixelColor(x, y);
                    if (px.alpha() == 0) continue;
                    ++opaque;
                    if (!nightSafe(px))
                        QFAIL(qPrintable(QStringLiteral("%1 pixel %2,%3 is %4")
                                             .arg(it.key())
                                             .arg(x)
                                             .arg(y)
                                             .arg(px.name(QColor::HexArgb))));
                }
            QVERIFY2(opaque > 0, qPrintable(it.key()));
        }
        const QImage boat = icons.value(OverlayIds::kBoatImage).convertToFormat(QImage::Format_ARGB32);
        const QColor centre = boat.pixelColor(boat.width() / 2, boat.height() / 2);
        QCOMPARE(centre.rgb(), overlayColours("night").boatFill.rgb());
    }

    void dayIconsUseDayColours() {
        const QImage boat =
            chartIcons(4.0, QStringLiteral("day")).value(OverlayIds::kBoatImage).convertToFormat(QImage::Format_ARGB32);
        QCOMPARE(boat.pixelColor(boat.width() / 2, boat.height() / 2).rgb(), overlayColours("day").boatFill.rgb());
    }
};

QTEST_MAIN(TstPalette)
#include "tst_palette.moc"
