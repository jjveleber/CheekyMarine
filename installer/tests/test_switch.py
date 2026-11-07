import os
import re
import unittest

from installer.tests.harness import Rig

STAMP = r"\d{8}T\d{6}Z"


class TestSwitch(unittest.TestCase):
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

    # ---- helpers -----------------------------------------------------------------------------

    def install(self, rel, env=None, ok=True, tty_answers=None):
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh", env=env, tty_answers=tty_answers)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def link(self, name):
        f = self.opt / name
        return os.readlink(f) if f.is_symlink() else None

    def sets(self):
        return sorted(os.listdir(self.opt / "sets"))

    def store_entries(self):
        return sorted(n for n in os.listdir(self.store))

    def lockval(self, rel, key):
        return re.search(r"(?m)^%s=(.*)$" % re.escape(key), (rel / "cheekymarine.lock").read_text()).group(1)

    def plant_db(self, text="live"):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        for sfx in ("", "-wal", "-shm"):
            self.db.with_name(self.db.name + sfx).write_text(text + sfx + "\n")

    def assert_complete(self, setdir):
        d = self.opt / "sets" / setdir
        for f in ("n2kd/usr/bin/n2kd", "plotter/bin/cheekyplotter", "plotter/PACK_SCHEMA",
                  "cheekymarine.lock", "cheekymarine.sh"):
            self.assertTrue((d / f).is_file(), "%s missing in %s" % (f, setdir))
        for pack in ("charts", "bathy"):
            links = [n for n in os.listdir(d / "packs") if n.startswith(pack + "-")]
            self.assertEqual(len(links), 1, links)
            self.assertTrue((d / "packs" / links[0] / "manifest.json").is_file())

    # ---- layout, upgrade, prune --------------------------------------------------------------

    def test_fresh_install_layout(self):
        rel = self.rig.make_set("0.1.0", "0.1.0")
        self.install(rel)
        cur = self.link("current")
        self.assertRegex(cur, r"^sets/0\.1\.0\.%s$" % STAMP)
        self.assertIsNone(self.link("previous"))
        c = self.opt / "current"
        for f in ("n2kd/usr/bin/n2kd", "plotter/bin/cheekyplotter", "cheekymarine.lock", "cheekymarine.sh"):
            self.assertTrue((c / f).is_file(), f)
        self.assertEqual((c / "cheekymarine.lock").read_text(), (rel / "cheekymarine.lock").read_text())
        self.assertEqual((c / "cheekymarine.sh").read_bytes(), (rel / "install-cheekymarine.sh").read_bytes())
        for pack in ("charts", "bathy"):
            name = "%s-puget-north-1.1.0" % pack
            l = c / "packs" / name
            self.assertTrue(l.is_symlink())
            self.assertEqual(os.readlink(l), "../../../packs/" + name)
            self.assertEqual(os.path.realpath(l), str((self.store / name).resolve()))
            self.assertTrue((l / "manifest.json").is_file())
            self.assertEqual((self.store / (name + ".sha256")).read_text().strip(),
                             self.lockval(rel, pack + ".sha256"))
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")
        self.assertEqual((self.opt / "bin/cheekymarine").read_bytes(), (rel / "install-cheekymarine.sh").read_bytes())
        self.assertFalse([n for n in os.listdir(self.opt) if n.startswith(".stage-")])
        self.assertIn("installed: 0.1.0", self.install(rel).stdout)

    def test_upgrade_sets_previous(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assertEqual(self.link("previous"), a_dir)
        self.assertEqual(len(self.sets()), 2)
        self.assert_complete(os.path.basename(a_dir))
        self.assert_complete(os.path.basename(self.link("current")))

    def test_third_set_prunes_oldest(self):
        rels = [self.rig.make_set(v, v) for v in ("0.1.0", "0.2.0", "0.3.0")]
        dirs = []
        for rel in rels:
            self.install(rel)
            dirs.append(os.path.basename(self.link("current")))
        self.assertEqual(self.sets(), sorted(dirs[1:]))
        self.assertEqual(self.link("previous"), "sets/" + dirs[1])

    def test_prune_keeps_packs_of_current_and_previous(self):
        a = self.rig.make_set("0.1.0", "0.1.0", charts_ver="1.0.0")
        b = self.rig.make_set("0.2.0", "0.1.0")
        c = self.rig.make_set("0.3.0", "0.2.0")
        self.install(a)
        self.install(b)
        self.assertEqual(self.store_entries(), [
            "bathy-puget-north-1.1.0", "bathy-puget-north-1.1.0.sha256",
            "charts-puget-north-1.0.0", "charts-puget-north-1.0.0.sha256",
            "charts-puget-north-1.1.0", "charts-puget-north-1.1.0.sha256"])
        self.install(c)
        self.assertEqual(self.store_entries(), [
            "bathy-puget-north-1.1.0", "bathy-puget-north-1.1.0.sha256",
            "charts-puget-north-1.1.0", "charts-puget-north-1.1.0.sha256"])

    def test_kill_mid_pack_unpack_refetches(self):
        rel = self.rig.make_set("0.1.0", "0.1.0")
        tmp = self.store / ".tmp-charts-puget-north-1.1.0"
        tmp.mkdir(parents=True)
        (tmp / "half").write_text("x")
        half = self.store / "bathy-puget-north-1.1.0"
        half.mkdir()
        (half / "junk").write_text("x")
        self.install(rel)
        self.assertFalse(tmp.exists())
        self.assertTrue([u for u in self.rig.downloads() if u.endswith("bathy-puget-north-1.1.0.tar")])
        self.assertFalse((half / "junk").exists())
        self.assertTrue((half / "manifest.json").is_file())
        self.assertEqual((self.store / "bathy-puget-north-1.1.0.sha256").read_text().strip(),
                         self.lockval(rel, "bathy.sha256"))
        self.assertFalse([n for n in os.listdir(self.store) if n.startswith(".tmp-")])

    def test_pack_schema_mismatch_leaves_current_untouched(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        self.install(a)
        a_dir = self.link("current")
        (self.rig.root / "calls").unlink()
        cases = [
            (self.rig.make_set("0.2.0", "0.2.0", charts_ver="1.2.0", bathy_ver="1.2.0", pack_schema=2,
                               lock_overrides={"charts.schema": "1", "bathy.schema": "1"}),
             "pack schema mismatch: charts-puget-north-1.2.0 manifest.json schema is 2, the lock says 1"),
            (self.rig.make_set("0.3.0", "0.3.0", plotter_range=(1, 2),
                               lock_overrides={"plotter.pack_schema_max": "1"}),
             "pack schema mismatch: plotter PACK_SCHEMA max is 2, the lock says 1"),
        ]
        for rel, msg in cases:
            r = self.install(rel, ok=False)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn(msg, r.stderr)
            self.assertEqual(self.link("current"), a_dir)
            self.assertIsNone(self.link("previous"))
            self.assertFalse([c for c in self.rig.calls() if c.startswith("pkill")])

    def test_rerun_same_set_keeps_previous(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        b1 = self.link("current")
        self.install(b)
        b2 = self.link("current")
        self.assertNotEqual(b1, b2)
        self.assertRegex(b2, r"^sets/0\.2\.0\.")
        self.assertEqual(self.link("previous"), a_dir)
        self.assertEqual(self.sets(), sorted([os.path.basename(a_dir), os.path.basename(b2)]))

    def test_rerun_kill_before_flip_keeps_running_set(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        self.install(b)
        b1 = self.link("current")
        r = self.install(b, env={"CM_TEST_DIE_AT": "before_flip"}, ok=False)
        self.assertEqual(r.returncode, -9)
        self.assertEqual(self.link("current"), b1)
        self.assertEqual(self.link("previous"), a_dir)
        self.assert_complete(os.path.basename(b1))

    def test_kill_before_flip_keeps_old_set(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        r = self.install(b, env={"CM_TEST_DIE_AT": "before_flip"}, ok=False)
        self.assertEqual(r.returncode, -9)
        self.assertEqual(self.link("current"), a_dir)
        self.assert_complete(os.path.basename(a_dir))
        target = [n for n in self.sets() if n.startswith("0.2.0.")]
        self.assertEqual(len(target), 1)
        self.assert_complete(target[0])
        (self.rig.root / "calls").unlink()
        self.install(b)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assertEqual(self.link("previous"), a_dir)
        self.assertIn("systemctl start n2kd", self.rig.calls())
        self.assertTrue([c for c in self.rig.calls() if c.startswith("systemd-run") and "cheekyplotter" in c])

    def test_kill_after_flip_rerun_finishes(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        a_dir = self.link("current")
        (self.rig.root / "calls").unlink()
        r = self.install(b, env={"CM_TEST_DIE_AT": "after_flip"}, ok=False)
        self.assertEqual(r.returncode, -9)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assert_complete(os.path.basename(self.link("current")))
        self.assertEqual(self.link("previous"), a_dir)
        self.assertNotIn("systemctl start n2kd", self.rig.calls())
        (self.rig.root / "calls").unlink()
        self.install(b)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assertEqual(self.link("previous"), a_dir)
        self.assertIn("systemctl start n2kd", self.rig.calls())
        self.assertTrue([c for c in self.rig.calls() if c.startswith("systemd-run") and "cheekyplotter" in c])
        self.assertEqual((self.opt / "bin/cheekymarine").read_bytes(), (b / "install-cheekymarine.sh").read_bytes())

    # ---- data rule ---------------------------------------------------------------------------

    def copies(self):
        return sorted(os.listdir(self.copies_dir)) if self.copies_dir.exists() else []

    def test_unlabeled_db_is_moved_aside(self):
        rel = self.rig.make_set("0.1.0", "0.1.0")
        self.plant_db()
        self.install(rel)
        got = self.copies()
        self.assertEqual(len(got), 3, got)
        base = [n for n in got if n.endswith(".db")][0]
        self.assertRegex(base, r"^plotter-unknown-%s\.db$" % STAMP)
        self.assertEqual(set(got), {base, base + "-wal", base + "-shm"})
        self.assertEqual((self.copies_dir / base).read_text(), "live\n")
        for sfx in ("", "-wal", "-shm"):
            self.assertFalse(self.db.with_name(self.db.name + sfx).exists())
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_plotter_stopped_before_db_copy(self):
        rel = self.rig.make_set("0.1.0", "0.1.0")
        self.install(rel)
        self.plant_db()
        self.rig.state("procs").write_text("cheekyplotter\n")
        wrap = self.rig.work / "wrap"
        wrap.mkdir()
        marker = self.rig.work / "pkill-saw"
        (wrap / "pkill").write_text(
            '#!/usr/bin/env bash\n'
            'case " $* " in *" -TERM "*) ls -A "%s" > "%s" 2>/dev/null || : > "%s" ;; esac\n'
            'exec "%s/pkill" "$@"\n' % (self.copies_dir, marker, marker, self.rig.SHIMS))
        (wrap / "pkill").chmod(0o755)
        before = set(self.copies())
        path = str(wrap) + os.pathsep + str(self.rig.SHIMS) + os.pathsep + os.environ["PATH"]
        self.install(rel, env={"PATH": path})
        self.assertIn("pkill -TERM -u %s -x cheekyplotter" % self.rig.user, self.rig.calls())
        self.assertEqual(set(marker.read_text().split()), before)
        new = sorted(set(self.copies()) - before)
        self.assertEqual(len(new), 3, new)
        base = [n for n in new if n.endswith(".db")][0]
        self.assertRegex(base, r"^plotter-0\.1\.0-%s\.db$" % STAMP)
        for sfx in ("", "-wal", "-shm"):
            self.assertEqual((self.copies_dir / (base + sfx)).read_text(), "live%s\n" % sfx)

    def test_forward_switch_keeps_live_db(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.plant_db("data from A")
        self.install(b)
        self.assertEqual(self.db.read_text(), "data from A\n")
        self.assertTrue([n for n in self.copies() if re.match(r"^plotter-0\.1\.0-%s\.db$" % STAMP, n)])
        self.assertEqual(self.label.read_text(), "set=0.2.0\nplotter=0.2.0\n")

    def test_older_plotter_restores_copy_of_target(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.plant_db("data from A")
        self.install(b)
        self.plant_db("data from B")
        self.install(a, tty_answers=["y"])  # a downgrade: confirm it
        self.assertEqual(self.db.read_text(), "data from A\n")
        self.assertEqual(self.db.with_name("plotter.db-wal").read_text(), "data from A-wal\n")
        self.assertTrue([n for n in self.copies() if re.match(r"^plotter-0\.2\.0-%s\.db$" % STAMP, n)])
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_older_plotter_without_copy_starts_fresh(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        self.plant_db("data from B")
        self.install(a, tty_answers=["y"])  # a downgrade: confirm it
        self.assertFalse(self.db.exists())
        self.assertTrue([n for n in self.copies() if re.match(r"^plotter-0\.2\.0-%s\.db$" % STAMP, n)])

    def test_downgrade_kill_before_flip_label_errs_newer(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.plant_db("data from A")
        self.install(b)
        self.plant_db("data from B")
        r = self.install(a, env={"CM_TEST_DIE_AT": "before_flip"}, ok=False, tty_answers=["y"])
        self.assertEqual(r.returncode, -9)
        self.assertRegex(self.link("current"), r"^sets/0\.2\.0\.")
        self.assertEqual(self.label.read_text(), "set=0.2.0\nplotter=0.2.0\n")
        self.plant_db("migrated by B")  # on reboot, B's plotter runs on the restored db
        self.install(a, tty_answers=["y"])
        self.assertNotEqual(self.db.read_text(), "migrated by B\n")
        self.assertEqual(self.db.read_text(), "data from A\n")
        saved = [n for n in self.copies() if re.match(r"^plotter-0\.2\.0-%s\.db$" % STAMP, n)]
        self.assertIn("migrated by B\n", [(self.copies_dir / n).read_text() for n in saved])
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_forward_kill_before_flip_keeps_db(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.plant_db("data from A")
        r = self.install(b, env={"CM_TEST_DIE_AT": "before_flip"}, ok=False)
        self.assertEqual(r.returncode, -9)
        self.assertEqual(self.label.read_text(), "set=0.2.0\nplotter=0.2.0\n")
        self.plant_db("more from A")  # on reboot, A's plotter runs on the db
        self.install(b)
        self.assertEqual(self.db.read_text(), "more from A\n")
        self.assertEqual(self.label.read_text(), "set=0.2.0\nplotter=0.2.0\n")

    def test_downgrade_kill_after_flip_label_is_exact(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(b)
        r = self.install(a, env={"CM_TEST_DIE_AT": "after_flip"}, ok=False, tty_answers=["y"])
        self.assertEqual(r.returncode, -9)
        self.assertRegex(self.link("current"), r"^sets/0\.1\.0\.")
        self.assertEqual(self.label.read_text(), "set=0.1.0\nplotter=0.1.0\n")

    def test_unique_name_never_reuses_a_dir(self):
        sets = self.opt / "sets"
        sets.mkdir(parents=True)
        r = self.rig.sh('CM_SOURCE_ONLY=1 . "$1"; d="$2/0.1.0.$(date -u +%Y%m%dT%H%M%SZ)"; mkdir "$d"; '
                        'n=$(unique_name "$2" 0.1.0. ""); [ "$2/$n" != "$d" ] && [ ! -e "$2/$n" ] && echo "$n"',
                        str(self.rig.SCRIPT), str(sets))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout.strip(), r"^0\.1\.0\.%s$" % STAMP)


if __name__ == "__main__":
    unittest.main()
