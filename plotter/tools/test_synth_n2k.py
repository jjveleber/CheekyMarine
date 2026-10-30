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


def generate(out):
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "synth_n2k.py"),
                    "--canboat", CANBOAT, "--out", out], check=True)


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
        """The first vessel line at or after s+1 seconds. n2kd publishes a tick before the frames
        stamped at the same time, so that line carries the values of the frames stamped s."""
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
        self.assertTrue(any(v["pos"] is None and T0 + 300 <= v["t"] < T0 + 320 for v in self.vessel))

    def test_depth_dropout(self):
        self.assertTrue(any(v["depth"] is None and T0 + 360 <= v["t"] < T0 + 377 for v in self.vessel))

    def test_ais_targets(self):
        full = [a for a in self.ais if len(a["targets"]) == 3]
        self.assertTrue(full)
        last = full[-1]["targets"]
        by_name = {t["name"]: t for t in last if t["name"]}
        self.assertEqual(by_name["TEST TUG"]["class"], "A")
        self.assertEqual(by_name["TEST SAIL"]["class"], "B")
        self.assertEqual(sorted(t["mmsi"] for t in last), [367000001, 367000002, 367000003])
        self.assertTrue(all(t["lat"] is not None for t in last))


if __name__ == "__main__":
    unittest.main()
