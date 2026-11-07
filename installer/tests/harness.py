"""Test rig for installer/cheekymarine.sh.

A Rig is one fake machine: a CM_ROOT tree (Ubuntu 24.04 by default), a file:// release base that
stands in for GitHub, and shims on PATH for the system commands the installer drives. Shims log
`name args` to $CM_ROOT/calls and keep small state files in $CM_ROOT/shim-state (see shims/_shim.sh).

    rig = Rig(); self.addCleanup(rig.cleanup)
    rel = rig.make_set("0.2.0", "0.3.0")            # releases for a whole set
    r = rig.run("install", script=rel / "install-cheekymarine.sh")
    rig.calls(), rig.downloads(), rig.state("groups").read_text()
"""

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

UBUNTU_2404 = 'PRETTY_NAME="Ubuntu 24.04.3 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\nID_LIKE=debian\n'

# Default gsettings values the gsettings shim reports before anything is set (GNOME defaults).
GSETTINGS_DEFAULTS = {
    ("org.gnome.desktop.session", "idle-delay"): "uint32 300",
    ("org.gnome.settings-daemon.plugins.power", "idle-dim"): "true",
    ("org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type"): "'suspend'",
    ("org.gnome.settings-daemon.plugins.power", "sleep-inactive-battery-type"): "'suspend'",
    ("org.gnome.desktop.screensaver", "lock-enabled"): "true",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _tar(top, files, gz):
    """Deterministic tar bytes. files: {relative name: bytes or (bytes, mode)}; all under top/."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        dirs = {top}
        for name in files:
            parts = name.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add(top + "/" + "/".join(parts[:i]))
        for d in sorted(dirs):
            info = tarfile.TarInfo(d)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            t.addfile(info)
        for name in sorted(files):
            data, mode = files[name] if isinstance(files[name], tuple) else (files[name], 0o644)
            info = tarfile.TarInfo(top + "/" + name)
            info.size, info.mode = len(data), mode
            t.addfile(info, io.BytesIO(data))
    raw = buf.getvalue()
    if not gz:
        return raw
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as g:
        g.write(raw)
    return out.getvalue()


class Rig:
    INSTALLER = HERE.parent
    SCRIPT = HERE.parent / "cheekymarine.sh"
    LOCK_TOOL = HERE.parent / "lock-tool.sh"
    SHIMS = HERE / "shims"

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cm-rig-")
        top = Path(self._tmp.name)
        self.root = top / "root"
        self.base = top / "releases"
        self.work = top / "work"
        for d in (self.root, self.base, self.work):
            d.mkdir()
        self.base_url = "file://" + str(self.base)
        self.user = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        self.home = Path(os.path.expanduser("~" + self.user))
        self.write("/etc/os-release", UBUNTU_2404)
        (self.root / str(self.home).lstrip("/")).mkdir(parents=True, exist_ok=True)
        st = self.root / "shim-state"
        st.mkdir()
        (st / "gsettings").write_text("".join("%s\t%s\t%s\n" % (s, k, v) for (s, k), v in GSETTINGS_DEFAULTS.items()))

    def cleanup(self):
        self._tmp.cleanup()

    # ---- the fake machine -------------------------------------------------------------------

    def path(self, p):
        """The CM_ROOT path for an absolute production path, like the script's `p`."""
        return self.root / str(p).lstrip("/")

    def write(self, p, text, mode=None):
        f = self.path(p)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        if mode is not None:
            f.chmod(mode)
        return f

    def state(self, name):
        """A shim state file, for example state("uname-m"), state("procs"), state("groups")."""
        return self.root / "shim-state" / name

    def plant_set(self, lock, name=None, current=True):
        """Plant a set dir by hand: sets/<name>/cheekymarine.lock, and point `current` at it."""
        lock = Path(lock)
        ver = re.search(r"(?m)^set=(.*)$", lock.read_text()).group(1)
        d = self.path("/opt/cheekymarine/sets") / (name or ver + ".planted")
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(lock, d / "cheekymarine.lock")
        if current:
            link = self.path("/opt/cheekymarine/current")
            if link.is_symlink():
                link.unlink()
            link.symlink_to("sets/" + d.name)
        return d

    def env(self, env=None, tty_answers=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("CM_")}
        e.update(
            PATH=str(self.SHIMS) + os.pathsep + os.environ["PATH"],
            CM_ROOT=str(self.root),
            CM_BASE_URL=self.base_url,
            CM_TTY=str(self.work / "no-tty"),
            SUDO_USER=self.user,
        )
        if tty_answers is not None:
            tty = self.work / "tty"
            tty.write_text("".join(a + "\n" for a in tty_answers))
            e["CM_TTY"] = str(tty)
        for k, v in (env or {}).items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        return e

    def run(self, *args, tty_answers=None, env=None, script=None):
        """Run the installer (the committed script, or `script`) as `bash SCRIPT args`."""
        return subprocess.run(["bash", str(script or self.SCRIPT), *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=self.env(env, tty_answers), timeout=120)

    def sh(self, cmd, *args, tty_answers=None, env=None):
        """Run a bash snippet in the rig environment ($1.. = args). Source the script with CM_SOURCE_ONLY=1."""
        return subprocess.run(["bash", "-c", cmd, "rig", *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=self.env(env, tty_answers), timeout=120)

    def calls(self):
        f = self.root / "calls"
        return f.read_text().splitlines() if f.exists() else []

    def downloads(self):
        f = self.root / "downloads"
        return f.read_text().splitlines() if f.exists() else []

    # ---- fake releases ----------------------------------------------------------------------

    def make_release(self, tag, asset, content):
        """Put `asset` in release `tag` and add or replace its line in the release SHA256SUMS.
        Same name with the same bytes is a no-op; different bytes raise ValueError."""
        data = content.encode() if isinstance(content, str) else content
        rel = self.base / tag
        rel.mkdir(exist_ok=True)
        f = rel / asset
        if f.exists():
            if f.read_bytes() != data:
                raise ValueError("release %s already has a different %s" % (tag, asset))
            return
        f.write_bytes(data)
        sums = rel / "SHA256SUMS"
        lines = [l for l in (sums.read_text().splitlines() if sums.exists() else []) if l.split("  ", 1)[1] != asset]
        lines.append("%s  %s" % (sha256(data), asset))
        sums.write_text("".join(l + "\n" for l in sorted(lines, key=lambda l: l.split("  ", 1)[1])))

    def _n2kd(self, ver, arch="x86_64"):
        unit = (REPO / "n2kd/systemd/n2kd.service.in").read_text().replace("@CMAKE_INSTALL_FULL_BINDIR@", "/usr/bin")
        files = {
            "usr/bin/n2kd": (b"#!/bin/sh\necho n2kd %s\n" % ver.encode(), 0o755),
            "usr/share/cheekymarine/canboat.json": b'{"PGNs": []}\n',
            "usr/lib/systemd/system/n2kd.service": unit.encode(),
            "usr/lib/sysusers.d/cheekymarine.conf": (REPO / "n2kd/systemd/cheekymarine.sysusers").read_bytes(),
            "LICENSE": b"fake license\n",
        }
        files["SHA256SUMS"] = "".join("%s  %s\n" % (sha256(v[0] if isinstance(v, tuple) else v), k)
                                      for k, v in sorted(files.items())).encode()
        return _tar("n2kd-%s-%s" % (ver, arch), files, gz=True)

    def _plotter(self, ver, rng):
        stub = ('#!/bin/sh\n[ -n "$CM_ROOT" ] && echo "cheekyplotter %s $*" >> "$CM_ROOT/calls"\nexit 0\n' % ver)
        files = {
            "bin/cheekyplotter": (stub.encode(), 0o755),
            "PACK_SCHEMA": ("min=%d\nmax=%d\n" % rng).encode(),
        }
        return _tar("cheekyplotter-%s-x86_64" % ver, files, gz=True)

    def _pack(self, pack, ver, schema):
        manifest = {"pack": pack, "region": "puget-north", "version": ver, "schema": schema,
                    "built": "2026-11-01T00:00:00Z", "files": [], "sources": [], "notice": "test"}
        files = {"manifest.json": (json.dumps(manifest, indent=2) + "\n").encode(),
                 "%s.mbtiles" % pack: b"fake tiles\n"}
        return _tar("%s-puget-north-%s" % (pack, ver), files, gz=False)

    def make_set(self, set_ver, plotter_ver, n2kd_ver="0.1.0", charts_ver="1.1.0", bathy_ver="1.1.0",
                 pack_schema=1, plotter_range=(1, 1), lock_overrides=None):
        """Build every release of one set under self.base and return the set release dir
        cheekymarine-v<set>/ holding install-cheekymarine.sh (lock embedded by lock-tool.sh),
        cheekymarine.lock and SHA256SUMS. Part releases with the same tag and asset as an earlier
        make_set must be identical (ValueError otherwise). lock_overrides: {key: value} applied to
        the lock after the real hashes, before embedding."""
        n2kd_tag, n2kd_asset = "v" + n2kd_ver, "n2kd-%s-x86_64.tar.gz" % n2kd_ver
        n2kd = self._n2kd(n2kd_ver)
        self.make_release(n2kd_tag, n2kd_asset, n2kd)
        self.make_release(n2kd_tag, "n2kd-%s-aarch64.tar.gz" % n2kd_ver, self._n2kd(n2kd_ver, "aarch64"))
        plotter_tag, plotter_asset = "plotter-v" + plotter_ver, "cheekyplotter-%s-x86_64.tar.gz" % plotter_ver
        plotter = self._plotter(plotter_ver, plotter_range)
        self.make_release(plotter_tag, plotter_asset, plotter)
        packs = {}
        for pack, ver in (("charts", charts_ver), ("bathy", bathy_ver)):
            tag, asset = "%s-puget-north-v%s" % (pack, ver), "%s-puget-north-%s.tar" % (pack, ver)
            data = self._pack(pack, ver, pack_schema)
            self.make_release(tag, asset, data)
            packs[pack] = (ver, tag, asset, data)
        lines = ["# CheekyMarine set lock. Format: see installer/README.md.", "schema=1", "set=" + set_ver]
        lines += ["n2kd.version=" + n2kd_ver, "n2kd.tag=" + n2kd_tag, "n2kd.asset=" + n2kd_asset,
                  "n2kd.sha256=" + sha256(n2kd)]
        for pack in ("charts", "bathy"):
            ver, tag, asset, data = packs[pack]
            lines += ["%s.version=%s" % (pack, ver), "%s.tag=%s" % (pack, tag), "%s.asset=%s" % (pack, asset),
                      "%s.sha256=%s" % (pack, sha256(data)), "%s.schema=%d" % (pack, pack_schema)]
        lines += ["plotter.version=" + plotter_ver, "plotter.tag=" + plotter_tag, "plotter.asset=" + plotter_asset,
                  "plotter.sha256=" + sha256(plotter), "plotter.pack_schema_min=%d" % plotter_range[0],
                  "plotter.pack_schema_max=%d" % plotter_range[1]]
        text = "".join(l + "\n" for l in lines)
        for k, v in (lock_overrides or {}).items():
            text, n = re.subn(r"(?m)^%s=.*$" % re.escape(k), "%s=%s" % (k, v), text)
            if n == 0:
                text += "%s=%s\n" % (k, v)
        rel = self.base / ("cheekymarine-v" + set_ver)
        if rel.exists():
            raise ValueError("set release %s already exists" % rel.name)
        rel.mkdir()
        lock = rel / "cheekymarine.lock"
        lock.write_text(text)
        script = rel / "install-cheekymarine.sh"
        subprocess.run([str(self.LOCK_TOOL), "embed", str(lock), str(self.SCRIPT), str(script)], check=True)
        script.chmod(0o755)
        rel.joinpath("SHA256SUMS").write_text("".join(
            "%s  %s\n" % (sha256((rel / n).read_bytes()), n) for n in ("cheekymarine.lock", "install-cheekymarine.sh")))
        return rel
