"""Tests for relocate_n2k.py; the n2kd case needs N2KD set.

Run: N2KD=build/n2kd/n2kd python3 -I plotter/tools/test_relocate_n2k.py
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
NAVIGATING = os.path.join(ROOT, "plotter", "tests", "fixtures", "n2k", "navigating.log")

sys.path.insert(0, HERE)
import relocate_n2k  # noqa: E402


def write(path, text):
    with open(path, "w", encoding="ascii") as f:
        f.write(text)


class RelocateUnitTest(unittest.TestCase):
    def test_raw_line_with_z_timestamp_parses(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "raw.log")
            write(p, "2020-08-22T13:52:52.882Z,2,129025,1,255,8,00,01,02,03,04,05,06,07\n")
            frames = relocate_n2k.read_frames(p)
        self.assertEqual(len(frames), 1)
        ts, can_id, data = frames[0]
        self.assertAlmostEqual(ts, 1598104372.882, places=3)  # 2020-08-22 13:52:52 UTC
        self.assertEqual(can_id, (2 << 26) | (129025 << 8) | 1)
        self.assertEqual(data, bytes(range(8)))

    def test_raw_dash_timestamp_is_utc(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "raw.log")
            write(p, "2020-08-22-13:52:52.882,2,129025,1,255,8,00,01,02,03,04,05,06,07\n")
            frames = relocate_n2k.read_frames(p)
        self.assertAlmostEqual(frames[0][0], 1598104372.882, places=3)

    def test_raw_z_separator_timestamp_parses(self):
        # The form in OpenSkipper's Kees sample: 2009-06-18Z09:46:01.129
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "raw.log")
            write(p, "2009-06-18Z09:46:01.129,2,129025,2,255,8,98,56,72,1f,65,a8,3b,03\n")
            frames = relocate_n2k.read_frames(p)
        self.assertEqual(len(frames), 1)
        self.assertAlmostEqual(frames[0][0], 1245318361.129, places=3)

    def test_transform_translate_and_rotate(self):
        lat, lon = relocate_n2k.transform(47.0, -122.0, (47.0, -122.0), (48.0, -123.0), 0)
        self.assertAlmostEqual(lat, 48.0, places=9)
        self.assertAlmostEqual(lon, -123.0, places=9)
        north = 1000.0 / relocate_n2k.M_PER_DEG
        lat, lon = relocate_n2k.transform(47.0 + north, -122.0, (47.0, -122.0), (48.0, -123.0), 90)
        east_m = (lon + 123.0) * relocate_n2k.M_PER_DEG * math.cos(math.radians(48.0))
        north_m = (lat - 48.0) * relocate_n2k.M_PER_DEG
        self.assertAlmostEqual(east_m, 1000.0, delta=1.0)
        self.assertAlmostEqual(north_m, 0.0, delta=1.0)

    def test_not_available_positions_pass_through(self):
        frame = (1.0, (2 << 26) | (129025 << 8) | 1, b"\xff" * 8)
        msgs = relocate_n2k.reassemble([frame])
        self.assertEqual(relocate_n2k.relocate(msgs, (48.0, -123.0), 0, CANBOAT), [frame])
        # signed-maximum pattern (129025 is int32): also not available
        frame = (1.0, (2 << 26) | (129025 << 8) | 1, b"\xff\xff\xff\x7f\xff\xff\xff\x7f")
        msgs = relocate_n2k.reassemble([frame])
        self.assertEqual(relocate_n2k.relocate(msgs, (48.0, -123.0), 0, CANBOAT), [frame])

    def test_other_pgns_and_incomplete_fast_packets_pass_through(self):
        other = (1.0, (2 << 26) | (127250 << 8) | 1, bytes(range(8)))
        orphan = (1.5, (4 << 26) | (129038 << 8) | 2, bytes([0x21]) + b"\x01" * 7)  # frame 1 without frame 0
        pos = (2.0, (2 << 26) | (129025 << 8) | 1, (int(47.5e7)).to_bytes(4, "little") + (int(-122.5e7)).to_bytes(4, "little", signed=True))
        out = relocate_n2k.relocate(relocate_n2k.reassemble([other, orphan, pos]), (48.0, -123.0), 0, CANBOAT)
        self.assertEqual(out[0], other)
        self.assertEqual(out[1], orphan)
        self.assertEqual(out[2][:2], pos[:2])
        self.assertNotEqual(out[2][2], pos[2])
        lat = int.from_bytes(out[2][2][:4], "little", signed=True) * 1e-7
        self.assertAlmostEqual(lat, 48.0, places=6)  # first position lands on --to


class RelocateCliTest(unittest.TestCase):
    def run_cli(self, frames, to):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "in.log"), os.path.join(d, "out.log")
            write(src, "".join("(%.6f) can0 %08X#%s\n" % (ts, cid, data.hex().upper()) for ts, cid, data in frames))
            return subprocess.run([sys.executable, "-I", os.path.join(HERE, "relocate_n2k.py"), src, out,
                                   "--to", to, "--canboat", CANBOAT], capture_output=True, text=True)

    def test_no_own_ship_position_exits_1(self):
        other = (1.0, (2 << 26) | (127250 << 8) | 1, bytes(range(8)))
        res = self.run_cli([other], "48.0,-123.0")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("no own-ship position (129025 or 129029): nothing moved", res.stderr)

    def test_out_of_range_result_is_an_error_not_a_traceback(self):
        pos = (2.0, (2 << 26) | (129025 << 8) | 1, (int(47.5e7)).to_bytes(4, "little") + (int(-122.5e7)).to_bytes(4, "little", signed=True))
        res = self.run_cli([pos], "48.0,300.0")  # a longitude past the field's range
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertTrue(res.stderr.startswith("error: position out of range"), res.stderr)
        self.assertNotIn("Traceback", res.stderr)


def vessel_ais(n2kd, log):
    res = subprocess.run([n2kd, "--replay", log, "--speed", "0", "--stdout", "--pgns", CANBOAT],
                         check=True, capture_output=True, text=True)
    vessels, ais = [], []
    for line in res.stdout.splitlines():
        if not line.startswith("{"):
            continue
        j = json.loads(line)
        (vessels if j["type"] == "vessel" else ais).append(j)
    return vessels, ais


class RelocateN2kdTest(unittest.TestCase):
    def test_relocated_navigating_matches_n2kd(self):
        n2kd = os.environ.get("N2KD")
        if not n2kd:
            raise unittest.SkipTest("N2KD not set")
        to = (47.7441216, -122.4728663)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.log")
            subprocess.run([sys.executable, "-I", os.path.join(HERE, "relocate_n2k.py"), NAVIGATING, out,
                            "--to", "%.7f,%.7f" % to, "--canboat", CANBOAT], check=True)
            with open(NAVIGATING) as a, open(out) as b:
                self.assertEqual(len(a.readlines()), len(b.readlines()))
            v0, a0 = vessel_ais(n2kd, NAVIGATING)
            v1, a1 = vessel_ais(n2kd, out)
        self.assertEqual(len(v0), len(v1))
        self.assertGreater(len(v0), 100)
        first = next(v["pos"] for v in v0 if v["pos"])
        dlat, dlon = to[0] - first["lat"], to[1] - first["lon"]
        for x, y in zip(v0, v1):
            for k in ("t", "sog", "cog", "hdg", "depth", "waterTemp"):
                self.assertEqual(x[k], y[k], k)
            if x["pos"] is None:
                self.assertIsNone(y["pos"])
                continue
            self.assertAlmostEqual(y["pos"]["lat"] - x["pos"]["lat"], dlat, delta=1e-6)
            self.assertAlmostEqual(y["pos"]["lon"] - x["pos"]["lon"], dlon, delta=1e-6)
        self.assertEqual(len(a0), len(a1))
        self.assertGreater(len(a0), 10)
        for x, y in zip(a0, a1):
            self.assertEqual(len(x["targets"]), len(y["targets"]))
            for tx, ty in zip(x["targets"], y["targets"]):
                self.assertEqual(tx["mmsi"], ty["mmsi"])
                self.assertAlmostEqual(ty["lat"] - tx["lat"], dlat, delta=1e-6)
                self.assertAlmostEqual(ty["lon"] - tx["lon"], dlon, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
