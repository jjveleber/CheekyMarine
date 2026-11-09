import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALLER = HERE.parent
TOOL = INSTALLER / "lock-tool.sh"
LOCK = INSTALLER / "cheekymarine.lock"
SCRIPT = INSTALLER / "cheekymarine.sh"

PACKS = ["charts-puget-north", "bathy-puget-north"]
PARTS = ["n2kd"] + ["pack." + _i for _i in PACKS] + ["plotter"]
KEYS = ["schema", "set"]
for _p in PARTS:
    KEYS += [_p + ".version", _p + ".tag", _p + ".asset", _p + ".sha256"]
    if _p.startswith("pack."):
        KEYS.append(_p + ".schema")
    if _p == "plotter":
        KEYS += ["plotter.pack_schema_min", "plotter.pack_schema_max"]


def parse(path):
    d = {}
    order = []
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        d[k] = v
        order.append(k)
    return d, order


def sha(b):
    return hashlib.sha256(b).hexdigest()


class LockCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.base = self.dir / "releases"
        self.lock = self.dir / "test.lock"
        self.hashes = {}
        text = LOCK.read_text()
        d, _ = parse(LOCK)
        for part in PARTS:
            tag, asset = d[part + ".tag"], d[part + ".asset"]
            content = (part + "-bytes").encode()
            self.hashes[part] = sha(content)
            rel = self.base / tag
            rel.mkdir(parents=True)
            (rel / asset).write_bytes(content)
            (rel / "SHA256SUMS").write_text("%s  %s\n" % (self.hashes[part], asset))
            text = re.sub(r"(?m)^%s\.sha256=.*$" % re.escape(part), "%s.sha256=%s" % (part, self.hashes[part]), text)
        self.lock.write_text(text)

    def tool(self, *args):
        env = dict(os.environ, CM_BASE_URL="file://" + str(self.base))
        return subprocess.run([str(TOOL), *args], capture_output=True, text=True, env=env)

    def set_key(self, key, val):
        t = self.lock.read_text()
        t = re.sub(r"(?m)^%s=.*$" % re.escape(key), "%s=%s" % (key, val), t)
        self.lock.write_text(t)


class TestLock(LockCase):
    def test_check_passes_on_matching_sums(self):
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_fails_naming_part_on_mismatch(self):
        self.set_key("pack.bathy-puget-north.sha256", "1" * 64)
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 1)
        self.assertIn("bathy", r.stderr)
        self.assertNotIn("charts", r.stderr)

    def test_check_fails_on_missing_release(self):
        self.set_key("plotter.tag", "plotter-v9.9.9")
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 1)
        self.assertIn("plotter", r.stderr)

    def test_fill_writes_hashes_and_keeps_order(self):
        for part in PARTS:
            self.set_key(part + ".sha256", "0" * 64)
        _, before = parse(self.lock)
        r = self.tool("fill", str(self.lock))
        self.assertEqual(r.returncode, 0, r.stderr)
        d, after = parse(self.lock)
        self.assertEqual(before, after)
        for part, h in self.hashes.items():
            self.assertEqual(d[part + ".sha256"], h)
        self.assertEqual(self.tool("check", str(self.lock)).returncode, 0)

    def test_lock_keys_are_complete(self):
        d, order = parse(LOCK)
        self.assertEqual(order, KEYS)
        self.assertEqual(len(order), 22)
        self.assertEqual(d["schema"], "2")

    def test_check_fails_when_pack_schema_outside_plotter_range(self):
        self.set_key("pack.charts-puget-north.schema", "2")
        env = dict(os.environ, CM_BASE_URL="file:///nonexistent")
        r = subprocess.run([str(TOOL), "check", str(self.lock)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("charts", r.stderr)
        self.assertIn("schema", r.stderr)

    def test_check_fails_naming_missing_or_non_numeric_schema_key(self):
        base = self.lock.read_text()
        for key in ("pack.charts-puget-north.schema", "pack.bathy-puget-north.schema",
                    "plotter.pack_schema_min", "plotter.pack_schema_max"):
            for val in (None, "", "x", "1.5"):
                if val is None:
                    self.lock.write_text(re.sub(r"(?m)^%s=.*\n" % re.escape(key), "", base))
                else:
                    self.lock.write_text(base)
                    self.set_key(key, val)
                r = self.tool("check", str(self.lock))
                self.assertEqual(r.returncode, 1, (key, val, r.stderr))
                self.assertIn("lock-tool: %s is missing or not a whole number" % key, r.stderr, (key, val))

    def add_pack(self, pid, schema, after="pack.bathy-puget-north.schema"):
        """Add a pack (with a release holding its asset) after the line AFTER."""
        kind, region = pid.split("-", 1)
        tag, asset, content = "%s-v1.0.0" % pid, "%s-1.0.0.tar" % pid, (pid + "-bytes").encode()
        rel = self.base / tag
        rel.mkdir(parents=True)
        (rel / asset).write_bytes(content)
        (rel / "SHA256SUMS").write_text("%s  %s\n" % (sha(content), asset))
        block = "".join(l + "\n" for l in ["pack.%s.version=1.0.0" % pid, "pack.%s.tag=%s" % (pid, tag),
                                            "pack.%s.asset=%s" % (pid, asset), "pack.%s.sha256=%s" % (pid, sha(content)),
                                            "pack.%s.schema=%d" % (pid, schema)])
        text = self.lock.read_text()
        self.lock.write_text(re.sub(r"(?m)^(%s=.*\n)" % re.escape(after), lambda m: m.group(1) + block, text))

    def lock_packs(self, lock):
        g = subprocess.run(["bash", "-c", 'source "$1"; lock_packs', "x", str(SCRIPT)],
                           capture_output=True, text=True, env=dict(os.environ, CM_SOURCE_ONLY="1", CM_LOCK_FILE=str(lock)))
        self.assertEqual(g.returncode, 0, g.stderr)
        return g.stdout.split()

    def test_schema2_lists_packs(self):
        self.add_pack("charts-sound-central", 1, after="pack.charts-puget-north.schema")
        self.add_pack("bathy-sound-central", 1)
        self.assertEqual(self.lock_packs(self.lock), ["charts-puget-north", "charts-sound-central",
                                                      "bathy-puget-north", "bathy-sound-central"])
        self.assertEqual(self.tool("check", str(self.lock)).returncode, 0)

    def test_check_rejects_pack_schema_out_of_range(self):
        self.set_key("plotter.pack_schema_max", "2")
        self.set_key("pack.bathy-puget-north.schema", "3")
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 1)
        self.assertIn("bathy-puget-north: schema 3 outside plotter range 1..2", r.stderr)
        self.set_key("pack.bathy-puget-north.schema", "0")
        self.assertEqual(self.tool("check", str(self.lock)).returncode, 1)

    def test_check_rejects_mixed_schema_per_kind(self):
        self.set_key("plotter.pack_schema_max", "2")
        self.add_pack("charts-sound-central", 2, after="pack.charts-puget-north.schema")
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 1)
        self.assertIn("charts packs have mixed schemas", r.stderr)

    def test_check_requires_a_charts_pack(self):
        t = self.lock.read_text()
        self.lock.write_text(re.sub(r"(?m)^pack\.charts-puget-north\..*\n", "", t))
        r = self.tool("check", str(self.lock))
        self.assertEqual(r.returncode, 1)
        self.assertIn("no charts pack", r.stderr)

    def test_fill_covers_added_packs(self):
        self.add_pack("charts-sound-central", 1, after="pack.charts-puget-north.schema")
        self.set_key("pack.charts-sound-central.sha256", "0" * 64)
        self.assertEqual(self.tool("fill", str(self.lock)).returncode, 0)
        self.assertEqual(parse(self.lock)[0]["pack.charts-sound-central.sha256"], sha(b"charts-sound-central-bytes"))

    def test_schema1_lock_is_refused_for_install(self):
        old = self.dir / "old.lock"
        old.write_text(LOCK.read_text().replace("schema=2", "schema=1", 1))
        r = subprocess.run(["bash", str(SCRIPT), "install"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, CM_LOCK_FILE=str(old), CM_ROOT=str(self.dir / "root")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("lock schema 1", r.stderr)
        self.assertFalse((self.dir / "root").exists())

    def test_embed_replaces_block_and_bash_parses(self):
        out = self.dir / "out.sh"
        r = self.tool("embed", str(self.lock), str(SCRIPT), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(subprocess.run(["bash", "-n", str(out)]).returncode, 0)
        d, _ = parse(self.lock)
        for key in ("set", "n2kd.sha256", "pack.charts-puget-north.schema", "plotter.pack_schema_max"):
            g = subprocess.run(
                ["bash", "-c", 'source "$1"; lock_get "$2"', "x", str(out), key],
                capture_output=True, text=True, env=dict(os.environ, CM_SOURCE_ONLY="1"))
            self.assertEqual(g.returncode, 0, g.stderr)
            self.assertEqual(g.stdout.strip(), d[key])

    def test_committed_script_embeds_committed_lock(self):
        g = subprocess.run(
            ["bash", "-c", 'source "$1"; lock_get n2kd.sha256', "x", str(SCRIPT)],
            capture_output=True, text=True, env=dict(os.environ, CM_SOURCE_ONLY="1"))
        self.assertEqual(g.stdout.strip(), parse(LOCK)[0]["n2kd.sha256"])


if __name__ == "__main__":
    unittest.main()
