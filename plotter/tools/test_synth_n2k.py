"""Replays the synthetic everett-pt-townsend scenario through n2kd and checks the JSON it publishes.

Run: N2KD=build/n2kd/n2kd python3 -I plotter/tools/test_synth_n2k.py
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CANBOAT = os.path.join(ROOT, "third_party", "canboat", "canboat.json")
T0 = 1798000000.0
T0_DAY = 1798056000.0
FIXTURES = os.path.join(ROOT, "plotter", "tests", "fixtures", "n2k")


sys.path.insert(0, HERE)
import synth_n2k  # noqa: E402


class EncoderRangeTest(unittest.TestCase):
    """Encoder.payload rejects values that would collide with reserved bit patterns."""

    @classmethod
    def setUpClass(cls):
        cls.enc = synth_n2k.Encoder(CANBOAT)

    def pack(self, pgn, **values):
        return self.enc.payload(pgn, values)

    def raw(self, pgn, payload, field_id):
        f = next(f for f in self.enc.pgns[pgn]["Fields"] if f["Id"] == field_id)
        return (int.from_bytes(payload, "little") >> f["BitOffset"]) & ((1 << f["BitLength"]) - 1)

    def test_unset_signed_field_is_the_signed_not_available_pattern(self):
        p = self.pack(127250, sid=0, heading=1.0, variation=0.2731, reference=1)  # no deviation
        self.assertEqual(self.raw(127250, p, "deviation"), 0x7FFF)
        self.assertEqual(self.raw(127250, p, "variation"), round(0.2731 / 0.0001))

    def test_unset_unsigned_field_is_all_ones(self):
        p = self.pack(128267, sid=0, depth=10.0, offset=-0.3)  # no range
        self.assertEqual(self.raw(128267, p, "range"), 0xFF)

    def test_in_range_accepted(self):
        self.pack(128267, depth=100.0)  # unsigned 32 bit, 0.01 m
        self.pack(128267, offset=-0.3)  # signed 16 bit, 0.001 m
        self.pack(128267, offset=32.766)  # largest signed value below the sign bit

    def test_not_available_pattern_rejected(self):
        with self.assertRaises(ValueError):
            self.pack(128267, depth=0xFFFFFFFF * 0.01)  # raw all ones

    def test_signed_overflow_into_sign_bit_rejected(self):
        with self.assertRaises(ValueError):
            self.pack(128267, offset=32.768)  # raw 0x8000 would read back as negative

    def test_signed_below_minimum_rejected(self):
        with self.assertRaises(ValueError):
            self.pack(128267, offset=-32.769)

    def test_signed_minus_one_lsb_is_not_available_pattern(self):
        with self.assertRaises(ValueError):
            self.pack(128267, offset=-0.001)  # raw -1 is all ones, not available


def generate(out, scenario=None, duration_s=None):
    cmd = [sys.executable, "-I", os.path.join(HERE, "synth_n2k.py"), "--canboat", CANBOAT, "--out", out]
    if scenario:
        cmd += ["--scenario", scenario]
    if duration_s is not None:
        cmd += ["--duration-s", str(duration_s)]
    subprocess.run(cmd, check=True)


class SynthN2kTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n2kd = os.environ.get("N2KD")
        if not n2kd:
            raise unittest.SkipTest("N2KD not set")
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "a.log")
            generate(log)
            res = subprocess.run([n2kd, "--replay", log, "--speed", "0", "--stdout", "--pgns", CANBOAT],
                                 check=True, capture_output=True, text=True)
            log2 = os.path.join(tmp, "b.log")
            generate(log2)
            with open(log, "rb") as a, open(log2, "rb") as b:
                cls.deterministic = a.read() == b.read()
        lines = [json.loads(l) for l in res.stdout.splitlines() if l.startswith("{")]
        cls.vessel = [l for l in lines if l["type"] == "vessel"]
        cls.ais = [l for l in lines if l["type"] == "ais"]

    def near(self, s, key=None):
        """The first vessel line at or after s+1 seconds. n2kd processes a frame and then ticks if one is
        due, so the tick at second s+1 carries the first frame stamped s+1 (the position) and the other
        values from the earlier seconds, those stamped s."""
        c = [v for v in self.vessel if v["t"] >= T0 + s + 1 - 1e-6 and (key is None or v[key] is not None)]
        return c[0]

    def test_deterministic(self):
        self.assertTrue(self.deterministic)

    def test_start_position(self):
        self.assertTrue(any(v["pos"] and abs(v["pos"]["lat"] - 47.98) < 1e-6
                            and abs(v["pos"]["lon"] + 122.23) < 1e-6 for v in self.vessel))

    def test_sog(self):
        v = self.near(60, "sog")
        self.assertLess(v["t"] - (T0 + 61), 1)
        self.assertLess(abs(v["sog"] - 3.0866), 0.01)

    def test_depth(self):
        v = self.near(75, "depth")
        self.assertLess(v["t"] - (T0 + 76), 1)
        self.assertLess(abs(v["depth"] - (30 + 25 * math.sin(2 * math.pi * 75 / 300))), 0.006)
        self.assertEqual(v["depthOffset"], -0.3)

    def test_heading_reference(self):
        self.assertEqual(self.near(60, "hdg")["hdgRef"], "Magnetic")

    def test_water_temp(self):
        self.assertLess(abs(self.near(60, "waterTemp")["waterTemp"] - 283.15), 0.01)

    def test_position_dropout(self):
        # n2kd holds the last position for a few seconds, so the published nulls sit inside the
        # generator's [300, 315) gap and none appear once the frames resume at 315.
        gap = [v for v in self.vessel if v["pos"] is None and v["t"] >= T0 + 60]
        self.assertTrue(gap)
        self.assertGreaterEqual(min(v["t"] for v in gap), T0 + 305 - 1e-6)  # n2kd holds the position 5 s
        self.assertLess(max(v["t"] for v in gap), T0 + 315)
        before = [v for v in self.vessel if T0 + 290 <= v["t"] <= T0 + 300]
        self.assertTrue(before)
        self.assertTrue(all(v["pos"] is not None for v in before))
        after = [v for v in self.vessel if v["t"] >= T0 + 315]
        self.assertTrue(after)
        self.assertTrue(all(v["pos"] is not None for v in after))

    def test_cog_and_variation(self):
        v = self.near(60, "cog")
        expected = synth_n2k.Track(synth_n2k.WAYPOINTS, synth_n2k.SPEED).at(60)[2]
        self.assertLess(abs(v["cog"] - expected), 1e-3)
        self.assertLess(abs(self.near(60, "variation")["variation"] - 0.2731), 1e-4)

    def test_depth_dropout(self):
        # Mirrors test_position_dropout: n2kd holds the last depth 5 s (kDepthMaxAge), so the nulls
        # sit inside the generator's [360, 372) gap and none appear once the frames resume at 372.
        # n2kd processes a frame and then ticks if one is due (Daemon.cpp), so the tick at second s
        # carries the first frame stamped s and the other values from earlier seconds. At T0 + 372 that
        # first frame is the position, so depth still reads null there (the held depth expired at 365);
        # the first line with a depth is the next tick, hence the edge below is inclusive and "after"
        # starts past 372.
        gap = [v for v in self.vessel if v["depth"] is None and v["t"] >= T0 + 60]
        self.assertTrue(gap)
        self.assertGreaterEqual(min(v["t"] for v in gap), T0 + 365 - 1e-6)
        self.assertLessEqual(max(v["t"] for v in gap), T0 + 372 + 1e-6)
        before = [v for v in self.vessel if T0 + 350 <= v["t"] <= T0 + 360]
        self.assertTrue(before)
        self.assertTrue(all(v["depth"] is not None for v in before))
        after = [v for v in self.vessel if v["t"] > T0 + 372 + 1e-6]
        self.assertTrue(after)
        self.assertTrue(all(v["depth"] is not None for v in after))

    def test_near_reads_the_frames_stamped_one_second_earlier(self):
        # near()'s contract, pinned on a value that changes: at s = 150 and 200 the depth moves
        # 0.52 and 0.26 m per second, so the line at or after T0 + s + 1 matches depth_m(s) and
        # neither neighbor. A change in n2kd's tick order fails here, not silently in test_sog.
        for s in (150, 200):
            d = self.near(s, "depth")["depth"]
            self.assertLess(abs(d - synth_n2k.depth_m(s)), 0.006)
            self.assertGreater(abs(d - synth_n2k.depth_m(s - 1)), 0.1)
            self.assertGreater(abs(d - synth_n2k.depth_m(s + 1)), 0.1)

    def test_ais_targets(self):
        full = [a for a in self.ais if len(a["targets"]) == 3]
        self.assertTrue(full)
        last = full[-1]["targets"]
        by_name = {t["name"]: t for t in last if t["name"]}
        self.assertEqual(by_name["TEST TUG"]["class"], "A")
        self.assertEqual(by_name["TEST SAIL"]["class"], "B")
        self.assertEqual(sorted(t["mmsi"] for t in last), [367000001, 367000002, 367000003])
        self.assertTrue(all(t["lat"] is not None for t in last))


def replay(scenario, duration_s=None):
    """(vessel lines, ais lines) of a scenario replayed through n2kd; skips without N2KD."""
    n2kd = os.environ.get("N2KD")
    if not n2kd:
        raise unittest.SkipTest("N2KD not set")
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "a.log")
        generate(log, scenario, duration_s)
        res = subprocess.run([n2kd, "--replay", log, "--speed", "0", "--stdout", "--pgns", CANBOAT],
                             check=True, capture_output=True, text=True)
    lines = [json.loads(l) for l in res.stdout.splitlines() if l.startswith("{")]
    return [l for l in lines if l["type"] == "vessel"], [l for l in lines if l["type"] == "ais"]


def flat(p, origin):
    """(east, north) meters of p from origin, flat earth."""
    return ((p[1] - origin[1]) * synth_n2k.M_PER_DEG * math.cos(math.radians(origin[0])),
            (p[0] - origin[0]) * synth_n2k.M_PER_DEG)


def dist_to_segment(p, a, b):
    px, py = flat(p, a)
    bx, by = flat(b, a)
    f = max(0.0, min(1.0, (px * bx + py * by) / (bx * bx + by * by)))
    return math.hypot(px - f * bx, py - f * by)


class ScenarioTestBase(unittest.TestCase):
    SCENARIO = None
    DURATION = None

    @classmethod
    def setUpClass(cls):
        cls.vessel, cls.ais = replay(cls.SCENARIO, cls.DURATION)
        cls.positions = [(v["t"], v["pos"]["lat"], v["pos"]["lon"]) for v in cls.vessel if v["pos"]]


class EverettUnchangedTest(unittest.TestCase):
    def test_everett_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "e.log")
            generate(out, "everett-pt-townsend")
            with open(out, "rb") as a, open(os.path.join(FIXTURES, "everett-pt-townsend.log"), "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_duration_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "d.log")
            generate(out, "navigating", 30)
            with open(out, encoding="ascii") as f:
                stamps = [float(l[1:l.index(")")]) for l in f]
        self.assertLess(max(stamps), synth_n2k.T0_DAY + 31)
        self.assertGreaterEqual(min(stamps), synth_n2k.T0_DAY)


class NavigatingTest(ScenarioTestBase):
    SCENARIO = "navigating"

    def test_speed_and_waypoints(self):
        sog = [v for v in self.vessel if v["sog"] is not None and v["t"] >= T0_DAY + 61 - 1e-6][0]["sog"]
        self.assertLess(abs(sog - synth_n2k.NAV_SPEED), 0.3)
        first = self.positions[0]
        self.assertLess(abs(first[1] - synth_n2k.NAV_WAYPOINTS[0][0]), 1e-6)
        self.assertLess(abs(first[2] - synth_n2k.NAV_WAYPOINTS[0][1]), 1e-6)
        wp1 = synth_n2k.NAV_WAYPOINTS[1]
        self.assertTrue(any(t >= T0_DAY + 500 and math.hypot(*flat((la, lo), wp1)) < 50
                            for t, la, lo in self.positions))

    def test_heading_wanders(self):
        h = [v["hdg"] for v in self.vessel if T0_DAY + 10 <= v["t"] <= T0_DAY + 70 and v["hdg"] is not None]
        span = math.degrees(max(h) - min(h))
        self.assertGreaterEqual(span, 2)
        self.assertLess(span, 5)

    def test_depth_profile(self):
        depths = [v["depth"] for v in self.vessel if v["depth"] is not None]
        self.assertLess(abs(depths[0] - 8), 1)
        self.assertGreater(max(depths), 110)


class BounceTest(unittest.TestCase):
    def test_bounce_keeps_the_boat_on_route(self):
        vessel, _ = replay("navigating", 2400)
        wp = synth_n2k.NAV_WAYPOINTS
        pts = [(v["pos"]["lat"], v["pos"]["lon"]) for v in vessel if v["pos"]]
        self.assertGreater(len(pts), 2000)
        for p in pts:
            self.assertLess(min(dist_to_segment(p, a, b) for a, b in zip(wp, wp[1:])), 200)

    def test_track_bounce_false_extrapolates(self):
        t = synth_n2k.Track(synth_n2k.FISH_WAYPOINTS, 1.34112)
        lat, lon, _ = t.at(1500)
        self.assertGreater(lon, synth_n2k.FISH_WAYPOINTS[1][1])
        b = synth_n2k.Track(synth_n2k.FISH_WAYPOINTS, 1.34112, bounce=True)
        lat, lon, cog = b.at(1500)
        self.assertLess(lon, synth_n2k.FISH_WAYPOINTS[1][1])
        self.assertLess(abs((cog - t.at(0)[2]) % (2 * math.pi) - math.pi), 1e-9)


class FishingTest(ScenarioTestBase):
    SCENARIO = "fishing"

    def test_trolls_back_and_forth(self):
        sog = [v["sog"] for v in self.vessel if v["sog"] is not None]
        self.assertTrue(all(abs(x - 1.34112) < 0.05 for x in sog))
        out = [lo for t, la, lo in self.positions if t < T0_DAY + 920]
        back = [lo for t, la, lo in self.positions if T0_DAY + 935 < t < T0_DAY + 1800]
        self.assertTrue(all(b >= a for a, b in zip(out, out[1:])))
        self.assertTrue(all(b <= a for a, b in zip(back, back[1:])))
        self.assertGreater(out[-1], back[-1] + 1e-4)
        depths = [v["depth"] for v in self.vessel if v["depth"] is not None]
        self.assertTrue(all(14.5 <= d <= 40.5 for d in depths))

    def test_one_ais_target(self):
        full = [a for a in self.ais if a["targets"]]
        last = full[-1]["targets"]
        self.assertEqual([t["mmsi"] for t in last], [367000011])
        self.assertEqual(last[0]["class"], "A")
        self.assertEqual(last[0]["name"], "TEST FERRY")


class StoppedTest(ScenarioTestBase):
    SCENARIO = "fishing-stopped"

    def test_stays_within_3_m_with_sog_zero(self):
        o = synth_n2k.FISH_WAYPOINTS[0]
        self.assertTrue(self.positions)
        for t, la, lo in self.positions:
            self.assertLess(math.hypot(*flat((la, lo), o)), 3)
        sog = [v["sog"] for v in self.vessel if v["sog"] is not None]
        self.assertTrue(sog)
        self.assertTrue(all(x == 0 for x in sog))


if __name__ == "__main__":
    unittest.main()
