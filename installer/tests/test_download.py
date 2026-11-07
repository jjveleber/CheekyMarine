import hashlib
import os
import re
import unittest

from installer.tests.harness import Rig


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)

    def lockval(self, rel, key):
        m = re.search(r"(?m)^%s=(.*)$" % re.escape(key), (rel / "cheekymarine.lock").read_text())
        return m.group(1)

    def stage(self, ver):
        return self.rig.path("/opt/cheekymarine/.stage-" + ver)

    def test_download_failure_leaves_current_untouched(self):
        rel_a = self.rig.make_set("0.2.0", "0.3.0")
        a = self.rig.plant_set(rel_a / "cheekymarine.lock")
        before = sorted(os.listdir(self.rig.path("/opt/cheekymarine/sets")))
        rel_b = self.rig.make_set("0.2.1", "0.3.1")
        (self.rig.base / "plotter-v0.3.1" / "cheekyplotter-0.3.1-x86_64.tar.gz").unlink()
        r = self.rig.run("install", script=rel_b / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("download failed: plotter %s/plotter-v0.3.1/cheekyplotter-0.3.1-x86_64.tar.gz"
                      % self.rig.base_url, r.stderr)
        link = self.rig.path("/opt/cheekymarine/current")
        self.assertEqual(os.readlink(link), "sets/" + a.name)
        self.assertEqual(sorted(os.listdir(self.rig.path("/opt/cheekymarine/sets"))), before)
        self.assertFalse(self.stage("0.2.1").exists())
        self.assertFalse([c for c in self.rig.calls() if c.startswith("systemctl")])

    def test_checksum_mismatch_names_part(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        (self.rig.base / "v0.1.0" / "n2kd-0.1.0-x86_64.tar.gz").write_bytes(b"tampered")
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("checksum mismatch: n2kd n2kd-0.1.0-x86_64.tar.gz", r.stderr)
        self.assertFalse(self.stage("0.2.0").exists())

    def test_set_script_checked_against_release_sums(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        sums = rel / "SHA256SUMS"
        sums.write_text(re.sub(r"(?m)^\w+(  install-cheekymarine.sh)$", "0" * 64 + r"\1", sums.read_text()))
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("checksum mismatch: set install-cheekymarine.sh", r.stderr)

    def test_downloads_use_fixed_urls_only(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        urls = self.rig.downloads()
        self.assertTrue(urls)
        shape = re.compile(r"^%s/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$" % re.escape(self.rig.base_url))
        for u in urls:
            self.assertRegex(u, shape)
        tags = {u.rsplit("/", 2)[1] for u in urls}
        self.assertEqual(tags, {"v0.1.0", "charts-puget-north-v1.1.0", "bathy-puget-north-v1.1.0",
                                "plotter-v0.3.0", "cheekymarine-v0.2.0"})
        self.assertNotIn("aarch64", "".join(urls))

    def plant_pack(self, rel, pack, sidecar):
        name = self.lockval(rel, pack + ".asset")[:-len(".tar")]
        store = self.rig.path("/opt/cheekymarine/packs")
        (store / name).mkdir(parents=True)
        (store / (name + ".sha256")).write_text(sidecar + "\n")
        return name

    def test_pack_in_store_not_downloaded(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        self.plant_pack(rel, "charts", self.lockval(rel, "charts.sha256"))
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        urls = self.rig.downloads()
        self.assertFalse([u for u in urls if u.endswith("charts-puget-north-1.1.0.tar")])
        self.assertTrue([u for u in urls if u.endswith("bathy-puget-north-1.1.0.tar")])

    def test_pack_with_wrong_sidecar_is_downloaded(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        self.plant_pack(rel, "charts", "f" * 64)
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue([u for u in self.rig.downloads() if u.endswith("charts-puget-north-1.1.0.tar")])

    def test_piped_install(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = self.rig.sh('cat "$1" | bash', str(rel / "install-cheekymarine.sh"))
        self.assertEqual(r.returncode, 0, r.stderr)
        urls = self.rig.downloads()
        self.assertIn("%s/plotter-v0.3.0/cheekyplotter-0.3.0-x86_64.tar.gz" % self.rig.base_url, urls)
        self.assertIn("%s/cheekymarine-v0.2.0/SHA256SUMS" % self.rig.base_url, urls)
        self.assertIn("%s/cheekymarine-v0.2.0/install-cheekymarine.sh" % self.rig.base_url, urls)


if __name__ == "__main__":
    unittest.main()
