import fcntl
import json
import os
import subprocess
import tarfile
import unittest

from installer.tests.harness import Rig


def first_line(text):
    return text.splitlines()[0] if text else ""


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)

    def test_refuses_non_ubuntu(self):
        self.rig.write("/etc/os-release", 'ID=debian\nVERSION_ID="12"\n')
        r = self.rig.run("install")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(first_line(r.stderr),
                         "cheekymarine: this installer needs Ubuntu 24.04 or newer; this system is debian 12")

    def test_refuses_ubuntu_2204(self):
        self.rig.write("/etc/os-release", 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="22.04"\n')
        r = self.rig.run("install")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(first_line(r.stderr),
                         "cheekymarine: this installer needs Ubuntu 24.04 or newer; this system is ubuntu 22.04")

    def test_accepts_ubuntu_2604(self):
        self.rig.write("/etc/os-release", 'ID=ubuntu\nVERSION_ID="26.04"\n')
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refuses_aarch64(self):
        self.rig.state("uname-m").write_text("aarch64\n")
        r = self.rig.run("install")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(first_line(r.stderr),
                         "cheekymarine: this installer needs an x86_64 machine; this one is aarch64")
        self.assertIn("uname -m", self.rig.calls())

    def test_refuses_root_without_sudo_user(self):
        r = self.rig.run("install", env={"SUDO_USER": None})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(first_line(r.stderr),
                         "cheekymarine: run this installer with sudo from the desktop user's account, not as root")

    def test_refuses_second_concurrent_run(self):
        lock = self.rig.root / "run" / "cheekymarine-install.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for cmd in ("install", "rollback"):
                r = self.rig.run(cmd)
                self.assertEqual(r.returncode, 1, cmd)
                self.assertEqual(first_line(r.stderr),
                                 "cheekymarine: another CheekyMarine install or rollback is running; "
                                 "wait for it to finish, then try again")
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = self.rig.run("install", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_install_stub_passes_preflight_and_creates_lock_dir(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = self.rig.run(script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.rig.root / "run" / "cheekymarine-install.lock").exists())

    def test_unknown_command(self):
        r = self.rig.run("frobnicate")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(first_line(r.stderr),
                         "cheekymarine: unknown command: frobnicate (use install, rollback or version)")

    def test_version_prints_set_and_parts(self):
        rel = self.rig.make_set("0.2.0", "0.3.0", n2kd_ver="0.1.1", charts_ver="1.2.0", bathy_ver="1.3.0")
        self.rig.plant_set(rel / "cheekymarine.lock")
        r = self.rig.run("version", script=rel / "install-cheekymarine.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "installed: 0.2.0",
            "  n2kd: 0.1.1",
            "  charts: 1.2.0",
            "  bathy: 1.3.0",
            "  plotter: 0.3.0",
        ])
        # The committed script embeds set 0.1.0, which differs from the installed 0.2.0.
        r = self.rig.run("version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "installed: 0.2.0")
        self.assertEqual(r.stdout.splitlines()[-1], "this script installs: 0.1.0")

    def test_version_no_set_installed(self):
        r = self.rig.run("version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["installed: none", "this script installs: 0.1.0"])

    def test_version_needs_no_preflight(self):
        self.rig.write("/etc/os-release", "ID=debian\n")
        r = self.rig.run("version", env={"SUDO_USER": None})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_source_only_does_not_run_main(self):
        r = self.rig.run("install", env={"CM_SOURCE_ONLY": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.rig.calls(), [])


class TestHarness(unittest.TestCase):
    """The harness itself: later tasks build on these behaviors."""

    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.cleanup)

    def test_make_set_lock_matches_release_sums(self):
        rel = self.rig.make_set("0.2.0", "0.3.0")
        r = subprocess.run([str(Rig.LOCK_TOOL), "check", str(rel / "cheekymarine.lock")], capture_output=True,
                           text=True, env=dict(os.environ, CM_BASE_URL=self.rig.base_url))
        self.assertEqual(r.returncode, 0, r.stderr)
        sums = (rel / "SHA256SUMS").read_text()
        self.assertIn("  install-cheekymarine.sh\n", sums)
        self.assertIn("  cheekymarine.lock\n", sums)

    def test_make_set_parts_have_real_layout(self):
        self.rig.make_set("0.2.0", "0.3.0", pack_schema=2, plotter_range=(1, 2))
        b = self.rig.base
        with tarfile.open(b / "plotter-v0.3.0" / "cheekyplotter-0.3.0-x86_64.tar.gz") as t:
            names = t.getnames()
            self.assertIn("cheekyplotter-0.3.0-x86_64/bin/cheekyplotter", names)
            ps = t.extractfile("cheekyplotter-0.3.0-x86_64/PACK_SCHEMA").read().decode()
            self.assertEqual(ps, "min=1\nmax=2\n")
            self.assertTrue(t.getmember("cheekyplotter-0.3.0-x86_64/bin/cheekyplotter").mode & 0o100)
        with tarfile.open(b / "charts-puget-north-v1.1.0" / "charts-puget-north-1.1.0.tar") as t:
            m = json.loads(t.extractfile("charts-puget-north-1.1.0/manifest.json").read())
            self.assertEqual(m["schema"], 2)
            self.assertEqual(m["pack"], "charts")
        with tarfile.open(b / "v0.1.0" / "n2kd-0.1.0-x86_64.tar.gz") as t:
            for n in ("usr/bin/n2kd", "usr/share/cheekymarine/canboat.json",
                      "usr/lib/systemd/system/n2kd.service", "usr/lib/sysusers.d/cheekymarine.conf",
                      "SHA256SUMS"):
                self.assertIn("n2kd-0.1.0-x86_64/" + n, t.getnames())
        self.assertIn("n2kd-0.1.0-aarch64.tar.gz", (b / "v0.1.0" / "SHA256SUMS").read_text())

    def test_make_set_twice_shares_identical_parts(self):
        self.rig.make_set("0.2.0", "0.3.0")
        self.rig.make_set("0.2.1", "0.3.0")
        with self.assertRaises(ValueError):
            self.rig.make_set("0.2.2", "0.3.0", plotter_range=(1, 2))

    def test_make_set_lock_overrides(self):
        rel = self.rig.make_set("0.2.0", "0.3.0", lock_overrides={"charts.schema": "7"})
        self.assertIn("charts.schema=7\n", (rel / "cheekymarine.lock").read_text())

    def test_curl_shim_logs_and_fetches(self):
        self.rig.make_release("x-v1", "a.bin", b"hello")
        url = self.rig.base_url + "/x-v1/a.bin"
        r = self.rig.sh('curl -fsSL "$1"', url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "hello")
        self.assertEqual(self.rig.downloads(), [url])
        self.assertEqual(self.rig.calls(), ["curl -fsSL " + url])

    def test_shims_return_real_codes(self):
        self.assertEqual(self.rig.sh("systemctl stop n2kd").returncode, 5)
        self.assertEqual(self.rig.sh("pkill -x cheekyplotter").returncode, 1)
        self.assertEqual(self.rig.sh("pgrep -x cheekyplotter").returncode, 1)
        self.rig.write("/etc/systemd/system/n2kd.service", "[Service]\n")
        self.assertEqual(self.rig.sh("systemctl start n2kd").returncode, 0)
        r = self.rig.sh("systemctl is-active n2kd.service")
        self.assertEqual((r.returncode, r.stdout), (0, "active\n"))
        self.assertEqual(self.rig.sh("systemctl stop n2kd").returncode, 0)
        self.assertEqual(self.rig.sh("systemctl is-active -q n2kd").returncode, 3)
        self.rig.state("procs").write_text("cheekyplotter\n")
        self.assertEqual(self.rig.sh("pgrep -u me -x cheekyplotter").returncode, 0)
        self.assertEqual(self.rig.sh("pkill -TERM -u me -x cheekyplotter").returncode, 0)
        self.assertEqual(self.rig.sh("pgrep -x cheekyplotter").returncode, 1)

    def test_groups_and_sysusers(self):
        self.assertEqual(self.rig.sh("usermod -aG cheekymarine me").returncode, 6)
        self.rig.write("/etc/sysusers.d/cheekymarine.conf", 'u cheekymarine - "CheekyMarine daemon" - -\n')
        self.assertEqual(self.rig.sh("systemd-sysusers").returncode, 0)
        self.assertEqual(self.rig.sh("usermod -aG cheekymarine me").returncode, 0)
        self.assertEqual(self.rig.sh("usermod -a -G cheekymarine me").returncode, 0)
        self.assertEqual(self.rig.state("groups").read_text(), "me cheekymarine\n")

    def test_gsettings_store_and_sudo_passthrough(self):
        s = "org.gnome.desktop.session"
        r = self.rig.sh("gsettings get %s idle-delay" % s)
        self.assertEqual(r.stdout, "uint32 300\n")
        r = self.rig.sh("sudo -u me dbus-run-session -- gsettings set %s idle-delay 0" % s)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rig.sh("gsettings get %s idle-delay" % s).stdout, "uint32 0\n")
        self.assertEqual(self.rig.sh("gsettings get %s nope" % s).returncode, 1)
        self.assertIn("sudo -u me dbus-run-session -- gsettings set %s idle-delay 0" % s, self.rig.calls())
        self.assertIn("gsettings set %s idle-delay 0" % s, self.rig.calls())

    def test_tty_answers(self):
        r = self.rig.sh('exec 8<"$CM_TTY"; read -r a <&8; read -r b <&8; echo "$a,$b"', tty_answers=["y", "n"])
        self.assertEqual(r.stdout, "y,n\n")
        r = self.rig.sh('[ -e "$CM_TTY" ] && echo tty || echo none')
        self.assertEqual(r.stdout, "none\n")


if __name__ == "__main__":
    unittest.main()
