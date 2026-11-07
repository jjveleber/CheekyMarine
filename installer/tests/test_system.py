import os
import re
import unittest

from installer.tests.harness import Rig

EXECSTART = ("ExecStart=/opt/cheekymarine/current/n2kd/usr/bin/n2kd --can can0 --rawlog "
             "/var/lib/cheekymarine/rawlog --pgns "
             "/opt/cheekymarine/current/n2kd/usr/share/cheekymarine/canboat.json")


class TestSystem(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)
        self.opt = self.rig.path("/opt/cheekymarine")

    def install(self, rel, env=None, ok=True):
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh", env=env)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def index(self, prefix, after=0):
        calls = self.rig.calls()
        for i, c in enumerate(calls):
            if i >= after and c.startswith(prefix):
                return i
        self.fail("no call starting with %r in %s" % (prefix, calls))

    def test_n2kd_unit_execstart_through_current(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        f = self.rig.path("/etc/systemd/system/n2kd.service")
        self.assertTrue(f.is_file() and not f.is_symlink())
        text = f.read_text()
        self.assertEqual(text.count("ExecStart="), 1)
        self.assertIn("\n" + EXECSTART + "\n", text)
        self.assertIn("\nUser=cheekymarine\n", text)
        self.assertIn("\nGroup=cheekymarine\n", text)
        self.assertIn("systemctl daemon-reload", self.rig.calls())
        self.assertIn("systemctl enable n2kd", self.rig.calls())
        self.assertEqual(self.rig.state("systemctl-enabled").read_text().split(), ["n2kd.service"])

    def test_n2kd_unit_written_after_flip(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        calls = self.rig.calls()
        # the unit is written after the flip: at daemon-reload time current already exists, and the
        # reload comes after the (earlier) sysusers call and before the n2kd start
        reload_i = max(i for i, c in enumerate(calls) if c == "systemctl daemon-reload")
        self.assertLess(self.index("systemd-sysusers"), self.index("systemctl enable n2kd"))
        self.assertLess(reload_i, self.index("systemctl enable n2kd"))
        self.assertLess(self.index("systemctl enable n2kd"), self.index("systemctl start n2kd"))

    def test_n2kd_unit_after_flip_with_kill_before(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        unit = self.rig.path("/etc/systemd/system/n2kd.service")
        unit.write_text("[Service]\nExecStart=/old\n")
        self.install(b, env={"CM_TEST_DIE_AT": "before_flip"}, ok=False)
        self.assertEqual(unit.read_text(), "[Service]\nExecStart=/old\n")

    def test_apt_uses_lock_timeout(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        apt = [c for c in self.rig.calls() if c.startswith("apt-get")]
        self.assertEqual(len(apt), 2)
        self.assertTrue(apt[0].startswith("apt-get -o DPkg::Lock::Timeout=600 update"), apt[0])
        self.assertTrue(apt[1].startswith(
            "apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends iproute2 libxkbcommon0"), apt[1])
        self.assertTrue(apt[1].endswith("libxcb-xfixes0 libxcb-xkb1"), apt[1])

    def apt_packages(self):
        return re.search(r'(?m)^CM_APT_PACKAGES="(.*)"$', Rig.SCRIPT.read_text()).group(1).split()

    def test_apt_skipped_when_every_package_installed(self):
        self.rig.state("dpkg-installed").write_text("".join(p + "\n" for p in self.apt_packages()))
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertFalse([c for c in self.rig.calls() if c.startswith("apt-get")], self.rig.calls())
        self.assertIn("dpkg-query -W", "\n".join(self.rig.calls()))
        self.assertIn("packages are already installed", r.stdout)

    def test_apt_runs_when_a_package_is_missing(self):
        self.rig.state("dpkg-installed").write_text("".join(p + "\n" for p in self.apt_packages()[1:]))
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        apt = [c for c in self.rig.calls() if c.startswith("apt-get")]
        self.assertEqual(len(apt), 2, apt)
        self.assertTrue(apt[0].endswith(" update"), apt[0])

    def test_apt_failure_leaves_current_untouched(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        cur = os.readlink(self.opt / "current")
        self.rig.state("apt-get-fail").write_text("100\n")
        r = self.install(b, ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(os.readlink(self.opt / "current"), cur)
        self.assertEqual([n for n in os.listdir(self.opt / "sets")], [cur.split("/")[1]])

    def test_sysusers_before_group_add(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertTrue(self.rig.path("/etc/sysusers.d/cheekymarine.conf").is_file())
        self.assertIn("cheekymarine", self.rig.state("sysgroups").read_text().split())
        self.assertLess(self.index("systemd-sysusers"), self.index("usermod"))
        self.assertIn("%s cheekymarine" % self.rig.user, self.rig.state("groups").read_text())
        self.assertIn("usermod -aG cheekymarine " + self.rig.user, self.rig.calls())

    def test_can0_rule_and_unit_contents(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        rule = self.rig.path("/etc/udev/rules.d/80-cheekymarine-can0.rules").read_text()
        self.assertEqual(rule, 'ACTION=="add", SUBSYSTEM=="net", KERNEL=="can0", TAG+="systemd", '
                               'ENV{SYSTEMD_WANTS}+="cheekymarine-can0.service"\n')
        unit = self.rig.path("/etc/systemd/system/cheekymarine-can0.service").read_text()
        self.assertIn("\nBindsTo=sys-subsystem-net-devices-can0.device\n", unit)
        self.assertIn("\nAfter=sys-subsystem-net-devices-can0.device\n", unit)
        self.assertIn("\nType=oneshot\n", unit)
        self.assertIn("\nRemainAfterExit=yes\n", unit)
        starts = re.findall(r"(?m)^ExecStart=(.*)$", unit)
        self.assertEqual(starts, ["/usr/sbin/ip link set can0 down",
                                  "/usr/sbin/ip link set can0 type can bitrate 250000 listen-only on",
                                  "/usr/sbin/ip link set can0 up"])
        self.assertNotIn("[Install]", unit)
        self.assertIn("udevadm control --reload", self.rig.calls())

    def test_can0_trigger_when_present(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        self.install(a)
        self.assertFalse([c for c in self.rig.calls() if c.startswith("udevadm trigger")])
        (self.rig.root / "calls").unlink()
        self.rig.path("/sys/class/net/can0").mkdir(parents=True)
        self.install(a)
        trig = [c for c in self.rig.calls() if c.startswith("udevadm trigger")]
        self.assertEqual(len(trig), 1)
        self.assertRegex(trig[0], r"^udevadm trigger --action=add \S*/sys/class/net/can0$")
        self.assertLess(self.index("udevadm control --reload"), self.index("udevadm trigger"))

    def test_first_install_survives_no_n2kd_and_no_plotter(self):
        # nothing runs: the pkill shim returns 1 and systemctl stop of an unknown unit 5
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertIn("installed: 0.1.0", r.stdout)
        self.assertIn("systemctl start n2kd", self.rig.calls())

    def test_n2kd_stopped_even_when_not_active(self):
        # `activating` (a crash restart loop), `failed` or `deactivating` are not `active`; the
        # switch must stop n2kd in every state
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.rig.state("systemctl-active").write_text("")
        (self.rig.root / "calls").unlink()
        self.install(b)
        calls = self.rig.calls()
        self.assertIn("systemctl stop n2kd", calls)
        self.assertLess(calls.index("systemctl stop n2kd"), self.index("systemctl start n2kd"))

    def test_group_add_skips_plotter_start_and_says_relogin(self):
        self.rig.login()
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertFalse([c for c in self.rig.calls() if c.startswith("systemd-run")])
        self.assertIn("Log out and back in (or reboot) to start the plotter.", r.stdout)

    def test_already_member_starts_plotter(self):
        self.rig.login()
        self.rig.add_to_group()
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertNotIn("usermod", " ".join(self.rig.calls()))
        run = [c for c in self.rig.calls() if c.startswith("systemd-run")]
        self.assertEqual(run, ["systemd-run --user --machine=%s@ --collect /opt/cheekymarine/bin/cheekyplotter"
                               % self.rig.user])
        self.assertNotIn("Log out and back in", r.stdout)

    def test_user_manager_without_group_says_relogin(self):
        # a rerun after the first install but before a new login: the user is in the group, but
        # the user manager that systemd-run --user starts the plotter from is not
        self.rig.login()
        self.rig.add_to_group()
        self.rig.user_manager(has_group=False)
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertIn("systemctl show --property=MainPID user@%d.service" % os.getuid(), self.rig.calls())
        self.assertFalse([c for c in self.rig.calls() if c.startswith("systemd-run")])
        self.assertIn("Log out and back in (or reboot) to start the plotter.", r.stdout)

    def test_user_manager_with_group_starts_plotter(self):
        self.rig.login()
        self.rig.add_to_group()
        self.rig.user_manager(has_group=True)
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertTrue([c for c in self.rig.calls() if c.startswith("systemd-run")])
        self.assertNotIn("Log out and back in", r.stdout)

    def test_no_session_or_wrong_session_says_relogin(self):
        self.rig.add_to_group()
        self.rig.state("loginctl-session").unlink(missing_ok=True)
        r = self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertFalse([c for c in self.rig.calls() if c.startswith("systemd-run")])
        self.assertIn("Log out and back in (or reboot) to start the plotter.", r.stdout)
        for typ, state in (("tty", "active"), ("wayland", "online")):
            (self.rig.root / "calls").unlink()
            self.rig.login()
            self.rig.state("loginctl-type").write_text(typ + "\n")
            self.rig.state("loginctl-state").write_text(state + "\n")
            r = self.install(self.rig.make_set("0.1.%d" % (len(typ) + len(state)), "0.1.0"))
            self.assertFalse([c for c in self.rig.calls() if c.startswith("systemd-run")], (typ, state))
            self.assertIn("Log out and back in", r.stdout)

    def test_x11_session_starts_plotter(self):
        self.rig.add_to_group()
        self.rig.login()
        self.rig.state("loginctl-type").write_text("x11\n")
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertTrue([c for c in self.rig.calls() if c.startswith("systemd-run")])

    def test_launcher_and_autostart(self):
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        l = self.opt / "bin/cheekyplotter"
        self.assertTrue(os.access(l, os.X_OK))
        self.assertIn("\nexec /opt/cheekymarine/current/plotter/bin/cheekyplotter --fullscreen "
                      '--packs /opt/cheekymarine/current/packs "$@"\n', l.read_text())
        self.assertTrue(l.read_text().startswith("#!/bin/sh\n"))
        d = self.rig.path(self.rig.home / ".config/autostart")
        f = d / "cheekyplotter.desktop"
        self.assertEqual(f.read_text(), "[Desktop Entry]\nType=Application\nName=CheekyMarine plotter\n"
                                        "Exec=/opt/cheekymarine/bin/cheekyplotter\n")
        uid = os.getuid()
        self.assertEqual(f.stat().st_uid, uid)
        self.assertEqual(d.stat().st_uid, uid)

    def test_new_config_dir_is_private(self):
        cfg = self.rig.path(self.rig.home / ".config")
        self.assertFalse(cfg.exists())
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertEqual(cfg.stat().st_mode & 0o777, 0o700)
        self.assertEqual((cfg / "autostart").stat().st_mode & 0o777, 0o755)

    def test_existing_config_dir_mode_kept(self):
        cfg = self.rig.path(self.rig.home / ".config")
        cfg.mkdir()
        cfg.chmod(0o750)
        self.install(self.rig.make_set("0.1.0", "0.1.0"))
        self.assertEqual(cfg.stat().st_mode & 0o777, 0o750)

    def test_installed_command_carries_set_lock(self):
        a = self.rig.make_set("0.1.0", "0.1.0")
        b = self.rig.make_set("0.2.0", "0.2.0")
        self.install(a)
        self.install(b)
        r = self.rig.run("version", script=self.opt / "bin/cheekymarine")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("installed: 0.2.0\n"), r.stdout)
        self.assertNotIn("this script installs", r.stdout)


if __name__ == "__main__":
    unittest.main()
