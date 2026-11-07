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

KEYS = ["schema", "set"]
for _p in ("n2kd", "charts", "bathy", "plotter"):
    KEYS += [_p + ".version", _p + ".tag", _p + ".asset", _p + ".sha256"]
    if _p in ("charts", "bathy"):
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
        for part in ("n2kd", "charts", "bathy", "plotter"):
            tag, asset = d[part + ".tag"], d[part + ".asset"]
            content = (part + "-bytes").encode()
            self.hashes[part] = sha(content)
            rel = self.base / tag
            rel.mkdir(parents=True)
            (rel / asset).write_bytes(content)
            (rel / "SHA256SUMS").write_text("%s  %s\n" % (self.hashes[part], asset))
            text = re.sub(r"(?m)^%s\.sha256=.*$" % part, "%s.sha256=%s" % (part, self.hashes[part]), text)
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
        self.set_key("bathy.sha256", "1" * 64)
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
        for part in ("n2kd", "charts", "bathy", "plotter"):
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
        self.assertEqual(d["schema"], "1")

    def test_check_fails_when_pack_schema_outside_plotter_range(self):
        self.set_key("charts.schema", "2")
        env = dict(os.environ, CM_BASE_URL="file:///nonexistent")
        r = subprocess.run([str(TOOL), "check", str(self.lock)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("charts", r.stderr)
        self.assertIn("schema", r.stderr)

    def test_embed_replaces_block_and_bash_parses(self):
        out = self.dir / "out.sh"
        r = self.tool("embed", str(self.lock), str(SCRIPT), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(subprocess.run(["bash", "-n", str(out)]).returncode, 0)
        d, _ = parse(self.lock)
        for key in ("set", "n2kd.sha256", "plotter.pack_schema_max"):
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
