import os
import re
import unittest

from installer.tests.harness import Rig

STAMP = r"\d{8}T\d{6}Z"
NOTHING = "cheekymarine: nothing to roll back to"
QUESTION = "Install 0.1.0 over 0.2.0? This is a downgrade. [y/N]"


class TestRollback(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)
        self.rig.add_to_group()
        self.rig.login()
        self.opt = self.rig.path("/opt/cheekymarine")
        self.store = self.opt / "packs"
        self.copies_dir = self.rig.path("/var/lib/cheekymarine/db-copies")
        self.label = self.rig.path("/var/lib/cheekymarine/db-label")
        self.db = self.rig.path(self.rig.home / ".local/share/cheekyplotter/plotter.db")
        self.unit = self.rig.path("/etc/systemd/system/n2kd.service")

    # ---- helpers -----------------------------------------------------------------------------

    def install(self, rel, ok=True, **kw):
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh", **kw)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def rollback(self, ok=True, env=None):
        env = dict({"CM_BASE_URL": "file:///nonexistent/unreachable"}, **(env or {}))
        r = self.rig.run("rollback", script=self.opt / "bin/cheekymarine", env=env)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def link(self, name):
        f = self.opt / name
        return os.readlink(f) if f.is_symlink() else None

    def sets(self):
        return sorted(os.listdir(self.opt / "sets"))

    def store_entries(self):
        return sorted(os.listdir(self.store))

    def copies(self):
        return sorted(os.listdir(self.copies_dir)) if self.copies_dir.exists() else []

    def write_db(self, text):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.db.write_text(text + "\n")

    def reset_log(self):
        for n in ("calls", "downloads"):
            f = self.rig.root / n
            if f.exists():
                f.unlink()

    def snapshot(self):
        """Everything a stopped downgrade must leave as it was."""
        return (self.link("current"), self.link("previous"), self.sets(), self.store_entries(),
                self.label.read_text() if self.label.exists() else None, self.copies(),
                self.db.read_text() if self.db.exists() else None)

    # ---- rollback ----------------------------------------------------------------------------

    def test_rollback_restores_pre_upgrade_db_and_keeps_newer_copy(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.write_db("a")
        self.install(b)
        self.write_db("b")
        self.rollback()
        self.assertEqual(self.db.read_text(), "a\n")
        self.assertEqual(self.db.stat().st_uid, os.getuid())
        newer = [n for n in self.copies() if re.match(r"^plotter-0\.2\.0-%s\.db$" % STAMP, n)]
        self.assertEqual(len(newer), 1, self.copies())
        self.assertEqual((self.copies_dir / newer[0]).read_text(), "b\n")
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_rollback_offline(self):
        a = self.rig.make_set("0.1.0", "0.1.0", charts_ver="1.0.0")
        b = self.rig.make_set("0.2.0", "0.2.0", charts_ver="1.1.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        b_dir = self.link("current")
        # mark the older set's unit so the rewrite from it is visible
        src = self.opt / a_dir / "n2kd/usr/lib/systemd/system/n2kd.service"
        src.write_text(src.read_text() + "# from the older set\n")
        self.reset_log()
        r = self.rollback()
        self.assertEqual(self.rig.downloads(), [])
        calls = self.rig.calls()
        self.assertFalse([c for c in calls if c.startswith("curl")], calls)
        self.assertFalse([c for c in calls if c.startswith("apt-get")], calls)
        self.assertFalse([c for c in calls if c.startswith("gsettings")], calls)
        self.assertEqual(self.link("current"), a_dir)
        self.assertIsNone(self.link("previous"))
        self.assertFalse((self.opt / "previous").exists())
        self.assertEqual(self.sets(), [os.path.basename(a_dir)])
        self.assertFalse((self.opt / b_dir).exists())
        self.assertIn("# from the older set", self.unit.read_text())
        self.assertIn("ExecStart=/opt/cheekymarine/current/n2kd/usr/bin/n2kd", self.unit.read_text())
        self.assertIn("systemctl daemon-reload", calls)
        self.assertIn("systemctl stop n2kd", calls)
        self.assertIn("systemctl start n2kd", calls)
        self.assertTrue([c for c in calls if c.startswith("systemd-run") and "cheekyplotter" in c], calls)
        charts = self.opt / "current/packs/charts-puget-north-1.0.0"
        self.assertEqual(os.path.realpath(charts), str((self.store / "charts-puget-north-1.0.0").resolve()))
        self.assertEqual(self.store_entries(), [
            "bathy-puget-north-1.1.0", "bathy-puget-north-1.1.0.sha256",
            "charts-puget-north-1.0.0", "charts-puget-north-1.0.0.sha256"])
        self.assertEqual((self.opt / "bin/cheekymarine").read_bytes(), (a / "install-cheekymarine.sh").read_bytes())
        self.assertIn("installed: 0.1.0", r.stdout)
        self.assertNotIn("this script installs", r.stdout)

    def test_rollback_to_schema1_set(self):
        a = self.rig.make_set("0.1.0", "0.1.0", charts_ver="1.0.0")
        b = self.rig.make_set("0.2.0", "0.2.0", packs=[("charts", "sound-central", "1.0.0"),
                                                       ("charts", "sound-south", "1.0.0"),
                                                       ("bathy", "sound-central", "1.0.0")])
        self.install(a)
        a_dir = self.link("current")
        # lay the first set out as 0.2.1 did: lock schema 1, charts.* and bathy.* keys, no merged dir
        lock = self.opt / a_dir / "cheekymarine.lock"
        text = lock.read_text().replace("schema=2\n", "schema=1\n", 1)
        text = re.sub(r"(?m)^pack\.(charts|bathy)-puget-north\.", r"\1.", text)
        lock.write_text(text)
        self.assertFalse((self.opt / a_dir / "packs/merged").exists())
        self.install(b)
        self.assertTrue((self.opt / self.link("current") / "packs/merged").is_dir())
        r = self.rollback()
        self.assertEqual(self.link("current"), a_dir)
        self.assertIsNone(self.link("previous"))
        self.assertEqual(sorted(os.listdir(self.opt / "current/packs")),
                         ["bathy-puget-north-1.1.0", "charts-puget-north-1.0.0"])
        for pack in os.listdir(self.opt / "current/packs"):  # listdir shows dangling links: resolve each one
            self.assertTrue(os.path.exists(self.opt / "current/packs" / pack / "manifest.json"), pack)
        self.assertEqual(r.stdout.splitlines(), ["installed: 0.1.0", "  n2kd: 0.1.0", "  charts: 1.0.0",
                                                 "  bathy: 1.1.0", "  plotter: 0.1.0"])
        self.assertEqual(self.rig.run("version", script=self.opt / "bin/cheekymarine").stdout.splitlines()[0],
                         "installed: 0.1.0")

    def test_second_rollback_refused(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.install(b)
        self.rollback()
        cur = self.link("current")
        self.reset_log()
        r = self.rollback(ok=False)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(NOTHING, r.stderr)
        self.assertEqual(self.link("current"), cur)
        self.assertFalse([c for c in self.rig.calls() if c.startswith(("pkill", "systemctl"))])

    def test_rollback_refused_when_previous_is_missing_dangling_or_current(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        r = self.rollback(ok=False)  # first install: no previous
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(NOTHING, r.stderr)
        self.install(b)
        prev = self.opt / "previous"
        cur = self.link("current")
        prev.unlink()
        prev.symlink_to("sets/0.0.9.gone")  # dangling
        r = self.rollback(ok=False)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(NOTHING, r.stderr)
        prev.unlink()
        prev.symlink_to(cur)  # a kill between the previous move and the flip
        r = self.rollback(ok=False)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn(NOTHING, r.stderr)
        self.assertEqual(self.link("current"), cur)

    def test_rollback_kill_before_flip_rerun_rolls_back(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        b_dir = self.link("current")
        r = self.rollback(ok=False, env={"CM_TEST_DIE_AT": "before_flip"})
        self.assertEqual(r.returncode, -9)
        self.assertEqual(self.link("current"), b_dir)
        self.assertEqual(self.link("previous"), a_dir)
        self.rollback()
        self.assertEqual(self.link("current"), a_dir)
        self.assertIsNone(self.link("previous"))

    def test_upgrade_after_rollback_is_ordinary(self):
        a = self.rig.make_set("0.1.0", "0.1.0", charts_ver="1.0.0")
        b = self.rig.make_set("0.2.0", "0.2.0", charts_ver="1.1.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        self.rollback()
        self.reset_log()
        r = self.install(b)
        self.assertNotIn("downgrade", r.stdout + r.stderr)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assertEqual(self.link("previous"), a_dir)
        got = self.rig.downloads()
        self.assertTrue([u for u in got if u.endswith("charts-puget-north-1.1.0.tar")], got)
        self.assertFalse([u for u in got if u.endswith("bathy-puget-north-1.1.0.tar")], got)
        self.assertEqual(self.store_entries(), [
            "bathy-puget-north-1.1.0", "bathy-puget-north-1.1.0.sha256",
            "charts-puget-north-1.0.0", "charts-puget-north-1.0.0.sha256",
            "charts-puget-north-1.1.0", "charts-puget-north-1.1.0.sha256"])

    # ---- downgrade through install -----------------------------------------------------------

    def test_downgrade_without_copy_starts_fresh(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        b_dir = self.link("current")
        self.write_db("b")
        r = self.install(a, tty_answers=["yes"])
        self.assertIn(QUESTION, r.stderr)
        self.assertRegex(self.link("current"), r"^sets/0\.1\.0\.")
        self.assertEqual(self.link("previous"), b_dir)
        self.assertFalse(self.db.exists())
        newer = [n for n in self.copies() if re.match(r"^plotter-0\.2\.0-%s\.db$" % STAMP, n)]
        self.assertEqual([(self.copies_dir / n).read_text() for n in newer], ["b\n"])
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_downgrade_asks_and_no_stops(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        self.write_db("b")
        before = self.snapshot()
        self.reset_log()
        for answers in (["n"], [""], []):
            r = self.install(a, ok=False, tty_answers=answers)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn(QUESTION, r.stderr)
            self.assertIn("cheekymarine: downgrade from 0.2.0 to 0.1.0 not confirmed; nothing was changed",
                          r.stderr)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.rig.downloads(), [])
            self.assertFalse([c for c in self.rig.calls()
                              if c.startswith(("apt-get", "pkill", "systemctl", "gsettings"))])
            self.assertFalse([n for n in os.listdir(self.opt) if n.startswith(".stage-")])

    def test_downgrade_without_tty_stops(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        before = self.snapshot()
        self.reset_log()
        r = self.install(a, ok=False)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("cheekymarine: 0.1.0 is older than the installed 0.2.0 (a downgrade), and there is no "
                      "terminal to confirm it; nothing was changed", r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.rig.downloads(), [])
        self.assertFalse([c for c in self.rig.calls() if c.startswith(("apt-get", "pkill", "systemctl"))])

    def test_downgrade_yes_then_the_two_prompts_share_the_terminal(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        r = self.install(a, tty_answers=["y", "y", "y"])
        self.assertIn(QUESTION, r.stderr)
        self.assertIn("Turn on automatic login", r.stderr)
        self.assertIn("Turn off the lock screen", r.stderr)
        self.assertIn("AutomaticLogin=%s" % self.rig.user, self.rig.path("/etc/gdm3/custom.conf").read_text())
        self.assertRegex(self.link("current"), r"^sets/0\.1\.0\.")

    def test_rerun_and_upgrade_do_not_ask(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        for rel in (a, b):
            r = self.install(rel)
            self.assertNotIn("downgrade", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
