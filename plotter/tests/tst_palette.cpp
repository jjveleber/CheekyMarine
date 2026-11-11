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

// Night vision rule (spec 4.1): amber on black.
bool amberSafe(const QColor& c) { return c.blue() <= 0x20 && c.green() <= 0.75 * c.red(); }

using ColourField = QColor OverlayColours::*;
const QList<ColourField> kFields{&OverlayColours::hullFill, &OverlayColours::hullOutline, &OverlayColours::cabin,
                           &OverlayColours::windshield, &OverlayColours::motor, &OverlayColours::motorOutline,
                           &OverlayColours::portLight, &OverlayColours::stbdLight, &OverlayColours::aisFill,
                           &OverlayColours::aisOutline, &OverlayColours::heading, &OverlayColours::cog,
                           &OverlayColours::aisVector, &OverlayColours::track};

bool near(const QColor& a, const QColor& b) {
    return std::abs(a.red() - b.red()) <= 8 && std::abs(a.green() - b.green()) <= 8 &&
           std::abs(a.blue() - b.blue()) <= 8;
}

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

    // Every applied palette is stored as lastPalette; an auto start without a fix begins in it, so a
    // night start does not flash the day palette.
    void autoStartsInLastPalette() {
        Rig r;
        QVERIFY(r.settings);
        r.make();
        r.vessel.setState(seattleAt(utc("2026-06-21T05:00:00Z"))); // night
        QCOMPARE(r.settings->lastPalette(), QStringLiteral("night"));
        r.settings->setPaletteMode("dusk");
        QCOMPARE(r.settings->lastPalette(), QStringLiteral("dusk"));
        r.settings->setPaletteMode("auto");
        QCOMPARE(r.settings->lastPalette(), QStringLiteral("night"));
        r.ctrl.reset();
        r.vessel.setLive(false); // restart with no position yet
        Settings reopened(*r.store);
        PaletteController c(reopened, r.vessel, [&r] { return r.now; });
        QCOMPARE(c.palette(), QStringLiteral("night"));
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

    void nightOverlayColoursAreAmber() {
        const OverlayColours c = overlayColours(QStringLiteral("night"));
        for (ColourField f : kFields) {
            const QColor col = c.*f;
            if (f == &OverlayColours::stbdLight) {
                QCOMPARE(col, QColor("#20A040"));
                continue;
            }
            QVERIFY2(amberSafe(col), qPrintable(col.name()));
        }
        QVERIFY(c.track.red() <= 0xC0 && c.track.green() <= 0x80);
    }

    void duskIsDayTowardBlack() {
        const OverlayColours day = overlayColours("day"), dusk = overlayColours("dusk");
        for (ColourField f : kFields) QCOMPARE(dusk.*f, towardBlack(day.*f, 0.45));
        QCOMPARE(towardBlack(QColor("#6E99BE"), 0.45), QColor(0x3d, 0x54, 0x69));
        QCOMPARE(towardBlack(QColor(10, 30, 255), 0.45), QColor(6, 16, 140)); // 5.5 -> 6, 16.5 -> 16 (half to even)
    }

    void trackColourPerPalette() {
        const QColor chosen("#444444");
        QCOMPARE(trackColour(chosen, "day"), chosen);
        QCOMPARE(trackColour(chosen, "dusk"), towardBlack(chosen, 0.45));
        QCOMPARE(trackColour(chosen, "night"), overlayColours("night").track);
        QCOMPARE(trackColour(QColor("#ff0000"), "night"), overlayColours("night").track);
    }

    void overlayColoursDifferPerPalette() {
        QVERIFY(overlayColours("day").hullFill != overlayColours("night").hullFill);
        QVERIFY(overlayColours("dusk").heading != overlayColours("night").heading);
    }

    // Each palette has a seamless 1024 px parchment for the no-data background; night's is red only.
    void backgroundPerPalette() {
        for (const QString& palette : {QStringLiteral("day"), QStringLiteral("dusk"), QStringLiteral("night")}) {
            const QImage img = chartBackground(palette);
            QVERIFY2(img.size() == QSize(1024, 1024), qPrintable(palette));
        }
        QVERIFY(chartBackground("day").pixelColor(512, 512).lightness() >
                chartBackground("dusk").pixelColor(512, 512).lightness());
        const QImage night = chartBackground("night").convertToFormat(QImage::Format_RGB32);
        for (int y = 0; y < night.height(); y += 7)
            for (int x = 0; x < night.width(); x += 7) {
                const QColor px = night.pixelColor(x, y);
                if (px.green() > 0x08 || px.blue() > 0x08 || px.red() > 0x30)
                    QFAIL(qPrintable(QStringLiteral("night %1,%2 is %3").arg(x).arg(y).arg(px.name())));
            }
    }

    void iconSizes() {
        const auto icons = chartIcons(4.0, QStringLiteral("day"));
        QCOMPARE(icons.size(), 5);
        QCOMPARE(icons.value(OverlayIds::kBoatImage).size(), QSize(36, 36));
        QCOMPARE(icons.value(OverlayIds::kAisImageA).size(), QSize(24, 24));
        QCOMPARE(icons.value(OverlayIds::kAisImageB).size(), QSize(18, 18));
        QCOMPARE(icons.value(OverlayIds::kAisImageHollow).size(), QSize(24, 24));
        QCOMPARE(icons.value(OverlayIds::kCogTipImage).width(), 16);
    }

    // Every opaque pixel of every night icon is amber, except blends with the starboard light inside
    // its bounding box (box x 30..33.5, y 37.5..44.5 of the 40 x 100 boat box).
    void nightIconsAreAmber() {
        const double pxPerMm = 12.0;
        const auto icons = chartIcons(pxPerMm, QStringLiteral("night"));
        QCOMPARE(icons.size(), 5);
        const QColor stbd("#20A040");
        for (auto it = icons.cbegin(); it != icons.cend(); ++it) {
            const QImage img = it.value().convertToFormat(QImage::Format_ARGB32);
            const double s = img.height() / 100.0, x0 = (img.width() - 40.0 * s) / 2.0;
            int opaque = 0, stbdPixels = 0;
            for (int y = 0; y < img.height(); ++y)
                for (int x = 0; x < img.width(); ++x) {
                    const QColor px = img.pixelColor(x, y);
                    if (px.alpha() < 16) continue; // unpremultiplying a faint edge pixel is mostly rounding noise
                    ++opaque;
                    const bool inLight = it.key() == QLatin1String(OverlayIds::kBoatImage) &&
                                         x >= x0 + 30 * s - 1 && x <= x0 + 33.5 * s + 1 &&
                                         y >= 37.5 * s - 1 && y <= 44.5 * s + 1;
                    if (inLight) {
                        if (near(px, stbd)) ++stbdPixels;
                        continue;
                    }
                    if (!amberSafe(px))
                        QFAIL(qPrintable(QStringLiteral("%1 pixel %2,%3 is %4")
                                             .arg(it.key()).arg(x).arg(y).arg(px.name(QColor::HexArgb))));
                }
            QVERIFY2(opaque > 0, qPrintable(it.key()));
            if (it.key() == QLatin1String(OverlayIds::kBoatImage)) QVERIFY(stbdPixels > 0);
        }
    }

    void dayIconsUseDayColours() {
        const auto icons = chartIcons(4.0, QStringLiteral("day"));
        const QImage boat = icons.value(OverlayIds::kBoatImage).convertToFormat(QImage::Format_ARGB32);
        QCOMPARE(boat.pixelColor(boat.width() / 2, boat.height() / 2).rgb(), overlayColours("day").cabin.rgb());
        const QImage ais = icons.value(OverlayIds::kAisImageA).convertToFormat(QImage::Format_ARGB32);
        QCOMPARE(ais.pixelColor(ais.width() / 2, ais.height() / 2 + 3).rgb(), overlayColours("day").aisFill.rgb());
    }

    void dayBoatHasHullAndLights() {
        const QImage boat =
            chartIcons(12.0, QStringLiteral("day")).value(OverlayIds::kBoatImage).convertToFormat(QImage::Format_ARGB32);
        const OverlayColours d = overlayColours("day");
        int hull = 0, portL = 0, portR = 0, stbdL = 0, stbdR = 0;
        const int mid = boat.width() / 2;
        for (int y = 0; y < boat.height(); ++y)
            for (int x = 0; x < boat.width(); ++x) {
                const QColor px = boat.pixelColor(x, y);
                if (px.alpha() != 255) continue;
                if (near(px, d.hullFill)) ++hull;
                if (near(px, d.portLight)) (x < mid ? portL : portR)++;
                if (near(px, d.stbdLight)) (x < mid ? stbdL : stbdR)++;
            }
        QVERIFY(hull > 0);
        QVERIFY(portL > 0 && portR == 0);
        QVERIFY(stbdR > 0 && stbdL == 0);
    }

    void cogTipIsHorizontalBar() {
        const QImage tip = chartIcons(12.0, QStringLiteral("day")).value(OverlayIds::kCogTipImage)
                               .convertToFormat(QImage::Format_ARGB32);
        QCOMPARE(tip.width(), tip.height());
        const int mid = tip.height() / 2;
        QCOMPARE(tip.pixelColor(0, mid).rgb(), overlayColours("day").cog.rgb());
        QCOMPARE(tip.pixelColor(tip.width() - 1, mid).rgb(), overlayColours("day").cog.rgb());
        QCOMPARE(tip.pixelColor(tip.width() / 2, 0).alpha(), 0);
    }
};

QTEST_MAIN(TstPalette)
#include "tst_palette.moc"
