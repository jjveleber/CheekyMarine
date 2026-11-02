"""Narrated demo videos of the live plotter: drive the app with xdotool, capture the window, lay a
voice-over on the step times.

usage: python engine.py DEMO.py tts|rehearse|record|mux [--root DIR] [--work DIR] [--out DIR]

  tts       synthesize the narration (cached per line) and print its length
  rehearse  run the steps with no capture; a small screenshot after each step, tiled in sheet.png
  record    capture, then mux
  mux       rebuild the MP4 from the last capture (after editing narration only)
  check     frames at the end of every narration line of the finished MP4, tiled in check.png
  open      launch the app (LAUNCH_ARGS, fresh data) and leave it running for `bash x.sh`
  close     stop what `open` started

DEMO.py defines TITLE (the MP4 name), STEPS (list of (narration, action)), and optionally
LAUNCH_ARGS (extra cheekyplotter args) and AFTER_RESTART (steps run after a quit and relaunch on
the same data dir). Narration may hold [[seconds]] pauses. Actions use the helpers below.

--root (required): the demo worktree, with build/n2kd/n2kd and build-plotter/plotter/cheekyplotter. --work: scratch for clips, captures, data (default .superpowers/demo/<DEMO stem>
under the main checkout). --out: MP4 folder (default /mnt/c/Users/jjvel/Videos/CheekyMarine).
"""
import argparse, asyncio, importlib.util, json, os, re, subprocess, sys, time, wave
from pathlib import Path

VOICE, RATE = "en-US-AndrewNeural", "+0%"
SIZE = "1280x800"
SOCK = f"/run/user/{os.getuid()}/cm-demo-n2k.sock"   # AF_UNIX paths max ~107 chars: keep it short
FIXTURE = "plotter/tests/fixtures/n2k/everett-pt-townsend.log"
PACKS = ("chartpack/work/charts/charts-puget-north-1.0.0", "chartpack/work/bathy/bathy-puget-north-1.0.0")

# ---- input helpers (window coordinates at 1280x800) ------------------------------------------

APP_PID = None   # set by App.launch: input and capture go only to the app this run started


def win():
    """This run's visible 1280x800 window. By PID, never by name alone: other sessions run the same
    app at the same size, and the app also owns hidden windows with the same name."""
    if APP_PID is None:
        raise SystemExit("no app launched by this run")
    ids = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(APP_PID)],
                         capture_output=True, text=True).stdout.split()
    for w in ids:
        g = subprocess.run(["xdotool", "getwindowgeometry", w], capture_output=True, text=True).stdout
        if SIZE in g:
            return w
    return None


def _xdo(*a):
    subprocess.run(["xdotool", *map(str, a)], check=True)


def tap(p, pause=0.6):
    _xdo("mousemove", "--window", win(), *p, "click", "1"); time.sleep(pause)


def hold(p, secs=1.2, pause=0.8):
    _xdo("mousemove", "--window", win(), *p, "mousedown", "1"); time.sleep(secs); _xdo("mouseup", "1"); time.sleep(pause)


def drag(a, b, pause=0.8, n=12):
    w = win(); _xdo("mousemove", "--window", w, *a, "mousedown", "1")
    for i in range(1, n + 1):
        _xdo("mousemove", "--window", w, a[0] + (b[0] - a[0]) * i // n, a[1] + (b[1] - a[1]) * i // n); time.sleep(0.04)
    _xdo("mouseup", "1"); time.sleep(pause)


def move(p):
    _xdo("mousemove", "--window", win(), *p)


def wait(s):
    time.sleep(s)


# The on-screen keyboard (Keyboard.qml) at 1280x800.
KEYS = {}
for _row, _y, _xs in (("qwertyuiop", 379, (245, 321, 398, 474, 551, 627, 704, 780, 857, 933)),
                      ("asdfghjkl", 456, (284, 361, 437, 514, 590, 666, 743, 819, 896)),
                      ("zxcvbnm", 532, (361, 437, 514, 590, 666, 743, 819))):
    KEYS.update(zip(_row, ((x, _y) for x in _xs)))
KEYS.update({str(d): (x, 303) for d, x in zip(range(1, 10), (245, 321, 398, 474, 551, 627, 704, 780, 857))})
KEYS["0"] = (933, 303)
KEYS[" "] = (590, 609)
SHIFT, BACK, KCANCEL, KDONE = (261, 532), (919, 532), (304, 609), (875, 609)


def type_text(text):
    for ch in text:
        if ch.isupper():
            tap(SHIFT, 0.25)
        tap(KEYS[ch.lower()], 0.3)


# ---- app lifecycle ------------------------------------------------------------------------------

class App:
    def __init__(self, root, work, packs):
        self.root, self.work, self.packs, self.pids = root, work, packs, []

    def launch(self, data, *args):
        if os.path.exists(SOCK):
            os.remove(SOCK)
        log = open(self.work / "n2kd.log", "w")
        self.pids.append(subprocess.Popen(
            [str(self.root / "build/n2kd/n2kd"), "--replay", str(self.root / FIXTURE), "--speed", "1", "--socket", SOCK,
             "--pgns", str(self.root / "third_party/canboat/canboat.json")], stdout=log, stderr=log).pid)
        time.sleep(0.5)
        log = open(self.work / "app.log", "w")
        self.pids.append(subprocess.Popen(
            [str(self.root / "build-plotter/plotter/cheekyplotter"), "--socket", SOCK, "--packs", str(self.packs),
             "--data", str(data), "--window", SIZE, *args],
            env={**os.environ, "QT_QPA_PLATFORM": "xcb"}, stdout=log, stderr=log).pid)
        global APP_PID
        APP_PID = self.pids[-1]
        for _ in range(150):
            if win():
                return win()
            time.sleep(0.1)
        raise SystemExit(f"no {SIZE} CheekyMarine window; see {self.work / 'app.log'}")

    def stop(self):
        """Only the processes this run started: other sessions may run the same binaries."""
        for pid in self.pids:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
        self.pids = []
        global APP_PID
        APP_PID = None
        time.sleep(1.5)


# ---- narration ----------------------------------------------------------------------------------

def clip(work, text, n):
    import edge_tts
    d = work / "tts"; d.mkdir(exist_ok=True)
    parts = []
    for i, chunk in enumerate(re.split(r"(\[\[[\d.]+\]\])", text)):
        chunk = chunk.strip()
        if not chunk:
            continue
        p = d / f"{n:02d}_{i}.wav"
        if chunk.startswith("[["):
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                w.writeframes(b"\0\0" * int(24000 * float(chunk[2:-2])))
        else:
            key = d / f"{n:02d}_{i}.txt"
            if not (p.exists() and key.exists() and key.read_text() == chunk):
                mp3 = p.with_suffix(".mp3")
                asyncio.run(edge_tts.Communicate(chunk, VOICE, rate=RATE).save(str(mp3)))
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(p)], check=True)
                key.write_text(chunk)
        parts.append(p)
    lst = d / f"{n:02d}.lst"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out = d / f"{n:02d}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), str(out)], check=True)
    with wave.open(str(out)) as w:
        return out, w.getnframes() / w.getframerate()


# ---- running --------------------------------------------------------------------------------------

def run_steps(steps, first, clips, log, shot=None):
    """A step lasts the longer of its narration (+0.7 s) and its action. Times are wall clock."""
    for i, (_, act) in enumerate(steps, first):
        t0 = time.time()
        log.append((i, t0))
        act()
        left = clips[i][1] + 0.7 - (time.time() - t0)
        if left > 0:
            time.sleep(left)
        if shot:
            shot(i)


def grab(path, scale=480):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "x11grab", "-window_id", win(), "-i", ":0",
                    "-frames:v", "1", "-vf", f"scale={scale}:-1", str(path)])


def tile(pattern, out, work):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob", "-i", pattern, "-vf", "tile=4x7", str(out)],
                   cwd=work, stderr=subprocess.DEVNULL)


def segments(demo):
    segs = [(demo.STEPS, 0)]
    if getattr(demo, "AFTER_RESTART", None):
        segs.append((demo.AFTER_RESTART, len(demo.STEPS)))
    return segs


def rehearse(demo, app, work, clips):
    for f in work.glob("r_*.png"):
        f.unlink()
    data = fresh(work)
    for k, (steps, first) in enumerate(segments(demo)):
        app.launch(data, *getattr(demo, "LAUNCH_ARGS", []))
        time.sleep(1.0 if k == 0 else 2.5)
        try:
            run_steps(steps, first, clips, [], lambda i: grab(work / f"r_{i:02d}.png"))
        finally:
            app.stop()
    tile("r_*.png", work / "sheet.png", work)
    print(work / "sheet.png")


def record(demo, app, work, clips, out):
    data = fresh(work)
    segs = []
    for k, (steps, first) in enumerate(segments(demo)):
        w = app.launch(data, *getattr(demo, "LAUNCH_ARGS", []))
        raw = work / f"seg{k}.mkv"
        # Wall-clock frame stamps: x11grab under load otherwise stamps by frame count and drifts.
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-use_wallclock_as_timestamps", "1", "-f", "x11grab",
                               "-framerate", "30", "-window_id", w, "-i", ":0", "-copyts", "-c:v", "libx264",
                               "-preset", "ultrafast", "-crf", "18", str(raw)], stdin=subprocess.PIPE)
        time.sleep(1.0 if k == 0 else 2.5)
        log = []
        try:
            run_steps(steps, first, clips, log)
            time.sleep(0.5)
        finally:
            ff.communicate(b"q")
            app.stop()
        first_frame = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                            "stream=start_time", "-of", "csv=p=0", str(raw)],
                                           capture_output=True, text=True).stdout.split()[0])
        segs.append([str(raw), [(i, t - first_frame) for i, t in log]])
    (work / "timing.json").write_text(json.dumps(segs))
    mux(demo, work, clips, out)


def mux(demo, work, clips, out):
    segs = json.loads((work / "timing.json").read_text())
    parts = []
    for k, (raw, log) in enumerate(segs):
        vid = work / f"v{k}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-vf", "setpts=PTS-STARTPTS", "-fps_mode", "cfr",
                        "-r", "30", "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p", str(vid)],
                       check=True)
        ins, filt = ["-i", str(vid)], []
        for j, (i, t) in enumerate(log):
            ins += ["-i", str(clips[i][0])]
            filt.append(f"[{j + 1}:a]adelay={int(t * 1000)}:all=1[a{j}]")
        filt.append("".join(f"[a{j}]" for j in range(len(log))) +
                    f"amix=inputs={len(log)}:normalize=0:dropout_transition=0,apad[aout]")
        part = work / f"part{k}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(filt), "-map", "0:v",
                        "-map", "[aout]", "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        str(part)], check=True)
        parts.append(part)
    (work / "parts.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    out.mkdir(parents=True, exist_ok=True)
    final = out / f"{demo.TITLE}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "parts.txt"),
                    "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
    print(final, f"{duration(final):.0f} s")


def check(demo, work, clips, out):
    final = out / f"{demo.TITLE}.mp4"
    segs = json.loads((work / "timing.json").read_text())
    for f in work.glob("c_*.png"):
        f.unlink()
    offset = 0.0
    for k, (_, log) in enumerate(segs):
        for i, t in log:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{offset + t + clips[i][1]:.2f}", "-i", str(final),
                            "-frames:v", "1", "-vf", "scale=480:-1", str(work / f"c_{i:02d}.png")],
                           stderr=subprocess.DEVNULL)
        offset += duration(work / f"part{k}.mp4")
    tile("c_*.png", work / "check.png", work)
    vol = subprocess.run(["ffmpeg", "-i", str(final), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    print(work / "check.png", *re.findall(r"(?:mean|max)_volume: \S+ dB", vol))


def duration(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.split()[-1])


def fresh(work):
    data = work / "data"
    subprocess.run(["rm", "-rf", str(data)]); data.mkdir()
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demo"); ap.add_argument("mode", choices=["tts", "rehearse", "record", "mux", "check", "open", "close"])
    ap.add_argument("--root", required=True); ap.add_argument("--work"); ap.add_argument("--out", default="/mnt/c/Users/jjvel/Videos/CheekyMarine")
    a = ap.parse_args()
    git = lambda *x: subprocess.run(["git", *x], capture_output=True, text=True, check=True).stdout.strip()
    root = Path(a.root).resolve()
    main_checkout = Path(git("-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    demo_path = Path(a.demo).resolve()
    work = Path(a.work or main_checkout / ".superpowers/demo" / demo_path.stem).resolve()
    work.mkdir(parents=True, exist_ok=True)
    packs = work / "packs"; packs.mkdir(exist_ok=True)
    for rel in PACKS:
        link = packs / Path(rel).name
        if not link.exists():
            link.symlink_to(main_checkout / rel)

    app = App(root, work, packs)
    pidfile = work / "open.pids"
    if a.mode == "close":
        app.pids = [int(x) for x in pidfile.read_text().split()] if pidfile.exists() else []
        app.stop(); pidfile.unlink(missing_ok=True)
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    spec = importlib.util.spec_from_file_location("demo", demo_path)
    demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)
    steps = demo.STEPS + list(getattr(demo, "AFTER_RESTART", []))
    clips = [clip(work, say, n) for n, (say, _) in enumerate(steps)]
    if "\u2014" in "".join(s for s, _ in steps):
        raise SystemExit("narration has an em dash; the owner never wants one")
    out = Path(a.out)
    if a.mode == "open":
        app.launch(fresh(work), *getattr(demo, "LAUNCH_ARGS", []))
        pidfile.write_text(" ".join(map(str, app.pids)))
        print("running; poke with bash x.sh, stop with: engine.py", a.demo, "close --root", a.root)
    elif a.mode == "tts":
        print(f"{sum(c[1] for c in clips) / 60:.1f} min of narration, {len(clips)} lines")
    elif a.mode == "rehearse":
        rehearse(demo, app, work, clips)
    elif a.mode == "record":
        record(demo, app, work, clips, out)
    elif a.mode == "mux":
        mux(demo, work, clips, out)
    else:
        check(demo, work, clips, out)


if __name__ == "__main__":
    main()
