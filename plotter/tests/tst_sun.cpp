#include "core/Sun.h"
#include <QtTest>
#include <cmath>

namespace {
constexpr double kSeattleLat = 47.6062, kSeattleLon = -122.3321;
constexpr double kTromsoLat = 69.6492, kTromsoLon = 18.9553;

QDateTime utc(const char* iso) { return QDateTime::fromString(QString::fromLatin1(iso), Qt::ISODate); }

// Minutes between an event and the expected UTC time, or a large number when the event is missing.
double errMin(const std::optional<QDateTime>& got, const QDateTime& want) {
    if (!got) return 1e9;
    return std::abs(double(got->toSecsSinceEpoch() - want.toSecsSinceEpoch())) / 60.0;
}

QString describe(const std::optional<QDateTime>& got) {
    return got ? got->toString(Qt::ISODate) : QStringLiteral("missing");
}
} // namespace

class TstSun : public QObject {
    Q_OBJECT
private slots:
    // Oracle: US Naval Observatory API (aa.usno.navy.mil/api/rstt/oneday, tz=0, fetched 2026-10-29),
    // Seattle 47.6062, -122.3321; each event within 2 minutes.
    void seattleMatchesUsno_data() {
        QTest::addColumn<QDate>("date");
        QTest::addColumn<QString>("sunset");
        QTest::addColumn<QString>("civilDusk");
        QTest::addColumn<QString>("civilDawn");
        QTest::addColumn<QString>("sunrise");
        QTest::newRow("equinox") << QDate(2026, 3, 20) << "02:21" << "02:52" << "13:41" << "14:12";
        QTest::newRow("june solstice") << QDate(2026, 6, 21) << "04:11" << "04:51" << "11:31" << "12:12";
        QTest::newRow("december solstice") << QDate(2026, 12, 21) << "00:20" << "00:56" << "15:19" << "15:55";
    }
    void seattleMatchesUsno() {
        QFETCH(QDate, date);
        QFETCH(QString, sunset);
        QFETCH(QString, civilDusk);
        QFETCH(QString, civilDawn);
        QFETCH(QString, sunrise);
        const SunEvents e = sunEvents(date, kSeattleLat, kSeattleLon);
        const auto at = [&](const QString& hhmm) {
            return QDateTime(date, QTime::fromString(hhmm, QStringLiteral("HH:mm")), QTimeZone::UTC);
        };
        const struct {
            const char* name;
            const std::optional<QDateTime>& got;
            QString want;
        } events[] = {{"sunset", e.sunset, sunset},
                      {"civil dusk", e.civilDusk, civilDusk},
                      {"civil dawn", e.civilDawn, civilDawn},
                      {"sunrise", e.sunrise, sunrise}};
        for (const auto& ev : events) {
            const double err = errMin(ev.got, at(ev.want));
            const QString msg = QStringLiteral("%1: got %2, want %3, error %4 min")
                                    .arg(QLatin1String(ev.name), describe(ev.got), ev.want)
                                    .arg(err, 0, 'f', 2);
            QVERIFY2(err <= 2.0, qPrintable(msg));
            QCOMPARE(ev.got->timeSpec(), Qt::UTC);
            QCOMPARE(ev.got->date(), date); // events lie within the UTC date asked for
        }
    }

    // Tromso, midsummer: the sun never sets, so no event falls on the date and it is day all day,
    // decided without any event of that date.
    void polarDayHasNoEventsAndIsDay() {
        const SunEvents e = sunEvents(QDate(2026, 6, 21), kTromsoLat, kTromsoLon);
        QVERIFY(!e.civilDawn && !e.sunrise && !e.sunset && !e.civilDusk);
        QCOMPARE(paletteAt(utc("2026-06-21T23:00:00Z"), kTromsoLat, kTromsoLon), Palette::Day);
        QCOMPARE(paletteAt(utc("2026-06-21T11:00:00Z"), kTromsoLat, kTromsoLon), Palette::Day);
    }

    // Tromso, midwinter: no sunrise or sunset, but civil twilight around noon (about 10:44Z).
    void polarNightHasTwilightOnly() {
        const SunEvents e = sunEvents(QDate(2026, 12, 21), kTromsoLat, kTromsoLon);
        QVERIFY(!e.sunrise && !e.sunset);
        QVERIFY(e.civilDawn && e.civilDusk);
        QVERIFY(*e.civilDawn < *e.civilDusk);
        QCOMPARE(paletteAt(utc("2026-12-21T10:45:00Z"), kTromsoLat, kTromsoLon), Palette::Dusk);
        QCOMPARE(paletteAt(utc("2026-12-21T18:00:00Z"), kTromsoLat, kTromsoLon), Palette::Night);
        QCOMPARE(paletteAt(utc("2026-12-21T03:00:00Z"), kTromsoLat, kTromsoLon), Palette::Night);
    }

    // At 47.6062 N, 80 W the April sunset crosses 00:00Z, drifting later each day, so one UTC date
    // has no sunset: USNO (fetched 2026-10-29) gives none on 2026-04-08, 00:00 on 04-09 and 00:01 on
    // 04-10. Which date of the pair loses it depends on seconds, so allow either. Right after
    // midnight of the date without a sunset it is dusk, decided by the sunset of the date before.
    void eventMissingFromUtcDate() {
        const double lat = 47.6062, lon = -80.0;
        QList<QDate> missing;
        for (QDate d(2026, 4, 4); d <= QDate(2026, 4, 13); d = d.addDays(1)) {
            const SunEvents e = sunEvents(d, lat, lon);
            QVERIFY(e.civilDawn && e.sunrise && e.civilDusk);
            if (!e.sunset) missing << d;
        }
        QCOMPARE(missing.size(), 1);
        const QDate m = missing[0];
        QVERIFY2(m == QDate(2026, 4, 8) || m == QDate(2026, 4, 9), qPrintable(m.toString(Qt::ISODate)));
        const SunEvents before = sunEvents(m.addDays(-1), lat, lon);
        const SunEvents on = sunEvents(m, lat, lon);
        const SunEvents after = sunEvents(m.addDays(1), lat, lon);
        QVERIFY(before.sunset && after.sunset);
        QCOMPARE(before.sunset->time().hour(), 23);
        QCOMPARE(after.sunset->time().hour(), 0);
        const QDateTime midnight(m, QTime(0, 0), QTimeZone::UTC);
        QCOMPARE(paletteAt(midnight.addSecs(60), lat, lon), Palette::Dusk);
        QCOMPARE(paletteAt(on.civilDusk->addSecs(60), lat, lon), Palette::Night);
        QCOMPARE(paletteAt(on.sunrise->addSecs(60), lat, lon), Palette::Day);
        QCOMPARE(paletteAt(QDateTime(m.addDays(1), QTime(0, 0), QTimeZone::UTC).addSecs(-60), lat, lon), Palette::Day);
        QCOMPARE(paletteAt(after.sunset->addSecs(60), lat, lon), Palette::Dusk);
    }

    // On the antimeridian the events match those a hair inside it, on either side.
    void antimeridianMatchesNeighbour_data() {
        QTest::addColumn<double>("lon");
        QTest::addColumn<double>("near");
        QTest::newRow("-180") << -180.0 << -179.99;
        QTest::newRow("180") << 180.0 << 179.99;
    }
    void antimeridianMatchesNeighbour() {
        QFETCH(double, lon);
        QFETCH(double, near);
        const double lat = 20.0;
        for (QDate d(2026, 3, 18); d <= QDate(2026, 3, 22); d = d.addDays(1)) {
            const SunEvents got = sunEvents(d, lat, lon);
            const SunEvents want = sunEvents(d, lat, near);
            for (const auto& [g, w] : {std::pair{got.civilDawn, want.civilDawn}, std::pair{got.sunrise, want.sunrise},
                                       std::pair{got.sunset, want.sunset}, std::pair{got.civilDusk, want.civilDusk}}) {
                QVERIFY2(w, qPrintable(d.toString(Qt::ISODate)));
                QVERIFY2(errMin(g, *w) < 1.0, qPrintable(d.toString(Qt::ISODate) + ": got " + describe(g) +
                                                          ", want " + describe(w)));
            }
            for (int h = 0; h < 24; h += 3) {
                const QDateTime t(d, QTime(h, 30), QTimeZone::UTC);
                QCOMPARE(paletteAt(t, lat, lon), paletteAt(t, lat, near));
            }
        }
    }

    void paletteNames() {
        QCOMPARE(paletteName(Palette::Day), QStringLiteral("day"));
        QCOMPARE(paletteName(Palette::Dusk), QStringLiteral("dusk"));
        QCOMPARE(paletteName(Palette::Night), QStringLiteral("night"));
    }
};

QTEST_APPLESS_MAIN(TstSun)
#include "tst_sun.moc"
