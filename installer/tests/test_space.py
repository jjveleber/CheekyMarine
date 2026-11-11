import os
import re
import unittest

from installer.tests.harness import Rig

MIB = 1024  # KiB
MARGIN = 256 * MIB  # the fixed part of the installer's margin, in KiB
TILES = 8 * 1024 * 1024  # bytes of fake tiles in each pack


class TestSpace(unittest.TestCase):
    """The free-space check (#96): after the downloads, before apt or anything under /opt changes."""

    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)

    def avail(self, kib):
        self.rig.state("df-avail-kb").write_text("%d\n" % kib)

    def opt(self, sub=""):
        return self.rig.path("/opt/cheekymarine" + sub)

    def listing(self, sub):
        d = self.opt(sub)
        return sorted(os.listdir(d)) if d.is_dir() else []

    def needed_mb(self, stderr):
        m = re.search(r"cheekymarine: not enough free disk space for set [0-9.]+: it needs about (\d+) MB "
                      r"on the filesystem that holds /opt/cheekymarine, and (\d+) MB is free\. "
                      r"Free up space, then run this again; nothing was changed", stderr)
        self.assertIsNotNone(m, stderr)
        return int(m.group(1)), int(m.group(2))

    def assert_df_on_opt(self):
        self.assertIn("df -Pk %s" % self.opt(), self.rig.calls())

    def test_short_space_refuses_and_changes_nothing(self):
        rel = self.rig.make_set("0.2.0", "0.3.0", tiles_bytes=TILES)
        self.avail(MARGIN + 8 * MIB)
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1, r.stderr)
        need, free = self.needed_mb(r.stderr)
        # two 8 MiB packs to unpack, plus 10 % and 256 MiB
        self.assertTrue(273 <= need <= 276, need)
        self.assertEqual(free, 264)
        self.assert_df_on_opt()
        self.assertFalse(self.opt("/current").is_symlink())
        self.assertEqual(self.listing("/sets"), [])
        self.assertEqual(self.listing("/packs"), [])
        self.assertFalse(self.opt("/.stage-0.2.0").exists())
        self.assertFalse([c for c in self.rig.calls() if c.startswith(("apt-get", "systemctl", "cheekyplotter"))])

    def test_enough_space_installs(self):
        rel = self.rig.make_set("0.2.0", "0.3.0", tiles_bytes=TILES)
        self.avail(MARGIN + 24 * MIB)
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_df_on_opt()
        self.assertTrue(os.readlink(self.opt("/current")).startswith("sets/0.2.0."))

    def test_packs_in_store_need_no_new_space(self):
        a = self.rig.make_set("0.2.0", "0.3.0", tiles_bytes=TILES)
        r = self.rig.run("install", script=a / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.rig.make_set("0.2.1", "0.3.1", tiles_bytes=TILES)
        self.avail(MARGIN + 8 * MIB)  # less than the 16 MiB of packs, which are already in the store
        r = self.rig.run("install", script=b / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.readlink(self.opt("/current")).startswith("sets/0.2.1."))

    def test_merged_copy_counts_packs_in_store(self):
        packs = [("charts", "puget-north", "1.1.0"), ("charts", "sound-central", "1.0.0"),
                 ("bathy", "puget-north", "1.1.0")]
        a = self.rig.make_set("0.2.0", "0.3.0", packs=packs, tiles_bytes=TILES)
        r = self.rig.run("install", script=a / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        cur = os.readlink(self.opt("/current"))
        sets, store = self.listing("/sets"), self.listing("/packs")
        b = self.rig.make_set("0.2.1", "0.3.1", packs=packs, tiles_bytes=TILES)
        self.avail(MARGIN + 8 * MIB)  # the merged charts copy needs 16 MiB, though no pack downloads
        r = self.rig.run("install", script=b / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1, r.stderr)
        need, _ = self.needed_mb(r.stderr)
        self.assertTrue(273 <= need <= 276, need)
        self.assertEqual(os.readlink(self.opt("/current")), cur)
        self.assertEqual(self.listing("/sets"), sets)
        self.assertEqual(self.listing("/packs"), store)
        self.assertFalse(self.opt("/.stage-0.2.1").exists())
        self.avail(MARGIN + 24 * MIB)
        r = self.rig.run("install", script=b / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.readlink(self.opt("/current")).startswith("sets/0.2.1."))

    def test_fresh_install_credits_the_deleted_stage(self):
        # The 0.3.0 shape: a kind that merges, nothing in the store. The stage (24 MiB of packs) is
        # deleted before the merge writes its 16 MiB, so the need is the 24 MiB unpack, not 40.
        packs = [("charts", "puget-north", "1.1.0"), ("charts", "sound-central", "1.0.0"),
                 ("bathy", "puget-north", "1.1.0")]
        rel = self.rig.make_set("0.2.0", "0.3.0", packs=packs, tiles_bytes=TILES)
        self.avail(MARGIN + 30 * MIB)
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refusal_names_leftover_set_dirs(self):
        a = self.rig.make_set("0.2.0", "0.3.0", tiles_bytes=TILES)
        r = self.rig.run("install", script=a / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.opt("/sets/0.2.1.20261101T000000Z").mkdir()  # left by a run that failed after unpack
        b = self.rig.make_set("0.2.1", "0.3.1", tiles_bytes=TILES)
        self.avail(1000)
        r = self.rig.run("install", script=b / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.needed_mb(r.stderr)
        self.assertIn("Set dirs left by failed runs (neither current nor previous uses them, safe to delete): "
                      "/opt/cheekymarine/sets/0.2.1.20261101T000000Z", r.stderr)
        self.assertNotIn(os.readlink(self.opt("/current"))[len("sets/"):], r.stderr)
        self.assertTrue(self.opt("/sets/0.2.1.20261101T000000Z").is_dir())

    def test_unreadable_free_space_refuses(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        self.rig.state("df-avail-kb").write_text("")  # df prints no number in the Available column
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("cheekymarine: cannot read the free disk space of /opt/cheekymarine; nothing was changed",
                      r.stderr)
        self.assertNotIn("integer expression", r.stderr)
        self.assertFalse(self.opt("/current").is_symlink())


if __name__ == "__main__":
    unittest.main()
