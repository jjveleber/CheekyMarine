# CheekyMarine

`n2kd` is a C++ NMEA 2000 daemon.

## Build and test

```bash
cmake -S . -B build
cmake --build build -j
ctest --test-dir build --output-on-failure
```

## Running n2kd

```
n2kd (--can IFACE | --replay FILE) [options]
  --can IFACE     read live frames from a SocketCAN interface (e.g. can0)
  --replay FILE   replay a candump -L or canboat RAW log
  --speed N       replay speed factor >= 0.001, 0 = as fast as possible (default 1)
  --socket PATH   Unix socket to serve JSON on (default /run/cheekymarine/n2k.sock)
  --stdout        print JSON snapshots to stdout instead of serving a socket
  --rawlog DIR    write raw frames to rotating candump -L files in DIR
  --pgns PATH     canboat.json PGN database (default: installed copy, else source tree)
  --hz N          publish rate in Hz (default 2)
  --no-claim      do not send an ISO address claim on the CAN bus
  --help, --version
```

Replay example:

```bash
build/n2kd/n2kd --replay n2kd/tests/fixtures/garmin-airmar.log --speed 5 --stdout
```

Behavior:

- Snapshots go out at `--hz`: a `vessel` snapshot every tick, and an `ais` snapshot when targets exist and either their content (ignoring `t` and per-target `age`) changed since the last one sent or a new client connected, plus one empty-targets `ais` snapshot when the last target expires. Socket clients first receive a `hello` line; `--stdout` prints snapshots only, one JSON object per line.
- Live ticks are scheduled on the monotonic clock, so wall clock steps do not pause publishing; snapshots carry wall time. In replay mode the clock is the timestamp of the last frame read, so freshness and ticks follow the log, not the wall clock. A final snapshot is printed at end of file, then n2kd exits 0.
- With `--can`, if the interface cannot be opened n2kd logs once and retries every 5 s while still serving clients. After opening it sends one ISO address claim (PGN 60928, fixed unique number) unless `--no-claim`; it never sends anything else.
- If the socket's parent directory is missing it is created.
- Exit codes: 0 clean stop (SIGTERM/SIGINT) or end of replay; 1 bad options, unopenable replay file or socket; 2 unreadable or unparsable `canboat.json`.

`cmake --install build` installs the binary, `canboat.json` and `lib/systemd/system/n2kd.service`.

## Cutting a release

1. Bump `VERSION` in the `project(...)` line of the root `CMakeLists.txt` and commit.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The `Release` workflow runs on the tag, builds and tests x86_64, cross-builds aarch64 (static libstdc++), and attaches `n2kd-X.Y.Z-x86_64.tar.gz` and `n2kd-X.Y.Z-aarch64.tar.gz` to a GitHub release. Each tarball contains `n2kd`, `n2kd.service`, `canboat.json`, `LICENSE`, `canboat-LICENSE` and `SHA256SUMS`.

The tag must equal the CMake project version (`scripts/check-version-tag.sh vX.Y.Z` checks this locally), otherwise the workflow fails before building.
