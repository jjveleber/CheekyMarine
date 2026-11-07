import os
import socket
import unittest

from installer.tests.harness import Rig

STOCK_CONF = """# GDM configuration storage
#
# See /usr/share/gdm/gdm.schemas for a list of available options.

[daemon]
# Uncomment the line below to force the login screen to use Xorg
#WaylandEnable=false

# Enabling automatic login
#  AutomaticLoginEnable = true
#  AutomaticLogin = user1

# Enabling timed login
#  TimedLoginEnable = true

[security]

[xdmcp]

[chooser]

[debug]
# Uncomment the line below to turn on debugging
#Enable=true
"""

PWR = "org.gnome.settings-daemon.plugins.power"
SS = "org.gnome.desktop.screensaver"
Q_LOGIN = ("Turn on automatic login for %s? Anyone who opens this tablet gets your desktop with no "
           "password. [y/N]")
Q_LOCK = "Turn off the lock screen? The screen will not ask for your password after it wakes. [y/N]"
LEFT = "Left as it is. To change it later: "
CMD_LOGIN = ("sudo sh -c 'f=/etc/gdm3/custom.conf; grep -q \"^\\[daemon\\]\" $f || echo \"[daemon]\" >> $f; "
             "sed -i -E \"/^[[:space:]]*AutomaticLogin(Enable)?[[:space:]]*=/d; "
             "/^\\[daemon\\]/a AutomaticLoginEnable=true\\nAutomaticLogin=%s\" $f'")
CMD_LOCK = ("gsettings set org.gnome.desktop.screensaver lock-enabled false"
            " && gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend false")


class TestDesktop(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)
        self.u = self.rig.user
        self.conf = self.rig.write("/etc/gdm3/custom.conf", STOCK_CONF)
        self.rel = self.rig.make_set("0.1.0", "0.1.0")

    def install(self, **kw):
        r = self.rig.run("install", script=self.rel / "install-cheekymarine.sh", **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def gs(self):
        d = {}
        for line in self.rig.state("gsettings").read_text().splitlines():
            s, k, v = line.split("\t")
            d[(s, k)] = v
        return d

    def test_power_settings_written_and_read_back(self):
        self.install()
        g = self.gs()
        self.assertEqual(g[("org.gnome.desktop.session", "idle-delay")], "uint32 0")
        self.assertEqual(g[(PWR, "idle-dim")], "false")
        self.assertEqual(g[(PWR, "sleep-inactive-ac-type")], "'nothing'")
        self.assertEqual(g[(PWR, "sleep-inactive-battery-type")], "'nothing'")
        calls = self.rig.calls()
        self.assertIn("gsettings get %s idle-dim" % PWR, calls)
        self.assertTrue(any(c.startswith("sudo -u %s -H " % self.u) and "gsettings set" in c for c in calls), calls)

    def test_yes_sets_autologin_and_lock(self):
        r = self.install(tty_answers=["y", "y"])
        text = self.conf.read_text()
        daemon = text.split("[daemon]")[1].split("[security]")[0]
        self.assertIn("\nAutomaticLoginEnable=true\n", daemon)
        self.assertIn("\nAutomaticLogin=%s\n" % self.u, daemon)
        self.assertIn("#  AutomaticLoginEnable = true\n", text)
        self.assertIn("[debug]", text)
        g = self.gs()
        self.assertEqual(g[(SS, "lock-enabled")], "false")
        self.assertEqual(g[(SS, "ubuntu-lock-on-suspend")], "false")
        self.assertIn(Q_LOGIN % self.u, r.stdout)
        self.assertIn(Q_LOCK, r.stdout)
        self.assertNotIn(LEFT, r.stdout)

    def test_no_answer_leaves_settings_and_asks_again(self):
        for _ in range(2):
            r = self.install(tty_answers=["n", "N"])
            self.assertEqual(self.conf.read_text(), STOCK_CONF)
            g = self.gs()
            self.assertEqual(g[(SS, "lock-enabled")], "true")
            self.assertEqual(g[(SS, "ubuntu-lock-on-suspend")], "true")
            self.assertIn(Q_LOGIN % self.u, r.stdout)
            self.assertIn(Q_LOCK, r.stdout)
            self.assertIn(LEFT + CMD_LOGIN % self.u, r.stdout)
            self.assertIn(LEFT + CMD_LOCK, r.stdout)

    def test_no_tty_leaves_settings_without_asking(self):
        r = self.install()
        self.assertEqual(self.conf.read_text(), STOCK_CONF)
        self.assertEqual(self.gs()[(SS, "lock-enabled")], "true")
        self.assertNotIn("[y/N]", r.stdout)
        self.assertIn(LEFT + CMD_LOGIN % self.u, r.stdout)
        self.assertIn(LEFT + CMD_LOCK, r.stdout)
        self.assertNotIn(str(self.rig.root), r.stdout.split("installed:")[0])

    def test_printed_login_command_works(self):
        r = self.install()
        line = [l for l in r.stdout.splitlines() if l.startswith(LEFT + "sudo sh -c")][0]
        cmd = line[len(LEFT + "sudo "):].replace("/etc/gdm3/custom.conf", "$CONF")
        variants = {
            "stock": (STOCK_CONF, 1),
            "twice": (STOCK_CONF, 2),
            "false": (STOCK_CONF.replace("[daemon]\n", "[daemon]\nAutomaticLoginEnable=false\n"), 1),
            "nodaemon": ("[security]\n\n[debug]\n", 1),
        }
        for name, (text, times) in variants.items():
            f = self.rig.write("/t/%s.conf" % name, text)
            for _ in range(times):
                run = self.rig.sh(cmd, env={"CONF": str(f)})
                self.assertEqual(run.returncode, 0, run.stderr)
            txt = f.read_text()
            self.assertEqual(txt.count("AutomaticLoginEnable=true"), 1, (name, txt))
            self.assertEqual(txt.count("AutomaticLogin=%s" % self.u), 1, (name, txt))
            self.assertNotIn("AutomaticLoginEnable=false", txt)
            g = self.rig.sh('CM_SOURCE_ONLY=1 . "$1"; ini_get "$2" daemon AutomaticLoginEnable; '
                            'ini_get "$2" daemon AutomaticLogin', str(Rig.SCRIPT), str(f))
            self.assertEqual(g.stdout, "true\n%s\n" % self.u, name)

    def test_already_set_asks_nothing(self):
        self.conf.write_text(STOCK_CONF.replace(
            "[daemon]\n", "[daemon]\nAutomaticLoginEnable = true\nAutomaticLogin=%s\n" % self.u))
        before = self.conf.read_text()
        g = self.rig.state("gsettings")
        g.write_text(g.read_text().replace("%s\tlock-enabled\ttrue" % SS, "%s\tlock-enabled\tfalse" % SS))
        r = self.install(tty_answers=["y", "y"])
        self.assertNotIn("[y/N]", r.stdout)
        self.assertNotIn(LEFT, r.stdout)
        self.assertEqual(self.conf.read_text(), before)

    def ini(self, text, *args):
        f = self.rig.write("/t/test.conf", text)
        script = 'CM_SOURCE_ONLY=1 . "$1"; shift; ini_set "$@"'
        r = self.rig.sh(script, str(Rig.SCRIPT), str(f), *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return f.read_text()

    def test_ini_set_keeps_other_lines(self):
        out = self.ini(STOCK_CONF, "daemon", "AutomaticLogin", "bob")
        self.assertIn("[daemon]\nAutomaticLogin=bob\n", out)
        self.assertEqual(out.replace("AutomaticLogin=bob\n", "", 1), STOCK_CONF)
        # replace an existing key with spaces around =, other sections untouched
        out2 = self.ini("[security]\nAutomaticLogin=x\n[daemon]\nAutomaticLogin = old\nOther=1\n",
                        "daemon", "AutomaticLogin", "bob")
        self.assertEqual(out2, "[security]\nAutomaticLogin=x\n[daemon]\nAutomaticLogin=bob\nOther=1\n")
        # no [daemon]: the section is created
        out3 = self.ini("[security]\nA=1\n", "daemon", "AutomaticLoginEnable", "true")
        self.assertEqual(out3, "[security]\nA=1\n\n[daemon]\nAutomaticLoginEnable=true\n")
        # ini_get ignores commented lines
        f = self.rig.write("/t/g.conf", STOCK_CONF)
        r = self.rig.sh('CM_SOURCE_ONLY=1 . "$1"; ini_get "$2" daemon AutomaticLoginEnable; echo "rc=$?"',
                        str(Rig.SCRIPT), str(f))
        self.assertEqual(r.stdout, "rc=0\n")

    def test_dev_tty_without_terminal_is_no_terminal(self):
        script = ('CM_SOURCE_ONLY=1 . "$1"; ask "Q? [y/N]" && echo "rc=0" || echo "rc=$?"')
        r = self.rig.sh('setsid -w bash -c \'%s\' x "$1"' % script, str(Rig.SCRIPT), env={"CM_TTY": None})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rc=2", r.stdout)
        self.assertNotIn("Q?", r.stdout)

    def test_ask_answers(self):
        script = 'CM_SOURCE_ONLY=1 . "$1"; for i in 1 2 3 4 5; do ask Q && echo yes || echo "no$?"; done'
        r = self.rig.sh(script, str(Rig.SCRIPT), tty_answers=["y", "YES", "n", "", "maybe"])
        self.assertEqual(r.stdout.replace("Q ", "").split(), ["yes", "yes", "no1", "no1", "no1"])

    def test_no_logind_file_written(self):
        self.install(tty_answers=["y", "y"])
        self.assertFalse(self.rig.path("/etc/systemd/logind.conf.d").exists())
        self.assertFalse(any("logind" in c for c in self.rig.calls()), self.rig.calls())

    def test_session_bus_used_when_present(self):
        uid = os.getuid()
        sock = self.rig.path("/run/user/%d/bus" % uid)
        sock.parent.mkdir(parents=True)
        s = socket.socket(socket.AF_UNIX)
        self.addCleanup(s.close)
        s.bind(str(sock))
        self.install()
        buses = self.rig.state("gsettings-bus").read_text().split("\n")
        self.assertIn("unix:path=%s" % sock, buses)
        self.assertNotIn("dbus-run-session", " ".join(self.rig.calls()))

    def test_dbus_run_session_without_bus(self):
        self.install()
        self.assertTrue(any(c.startswith("dbus-run-session") or " dbus-run-session " in c
                            for c in self.rig.calls()), self.rig.calls())


if __name__ == "__main__":
    unittest.main()
