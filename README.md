# CheekyMarine

<p align="center"><img src="docs/assets/CheekyMarine-logo.jpg" alt="CheekyMarine: DIY chartplotter" width="704"></p>

A DIY second helm display for a small boat: an NMEA 2000 daemon, chart packs and a Qt chart plotter on a Raspberry Pi 5. Design: `docs/superpowers/specs/2026-10-28-cheekymarine-design.md`.

`n2kd` is a C++ NMEA 2000 daemon.

## Build and test

Prerequisites: CMake 3.25 or newer, GCC 13 or newer (or another compiler whose standard library has C++23 `std::expected`), and network access at configure time: CMake FetchContent downloads nlohmann/json v3.12.0 and, for the tests, Catch2 v3.16.1. Both are pinned by git tag, not by commit hash.

```bash
cmake -S . -B build
cmake --build build -j
ctest --test-dir build --output-on-failure
```

The chart pack tool (`chartpack`, Python) is built and tested separately: see [chartpack/README.md](chartpack/README.md).

## Running n2kd

```
usage: n2kd (--can IFACE | --replay FILE) [options]
  --can IFACE     read live frames from a SocketCAN interface (e.g. can0)
  --replay FILE   replay a candump -L or canboat RAW log
  --speed N       replay speed factor >= 0.001, 0 = as fast as possible (default 1)
  --socket PATH   Unix socket to serve JSON on (default /run/cheekymarine/n2k.sock)
  --stdout        print JSON snapshots to stdout instead of serving a socket
  --rawlog DIR    write raw frames to rotating candump -L files in DIR
  --pgns PATH     canboat.json PGN database (default: installed copy, else source tree)
  --hz N          publish rate in Hz (default 2)
  --max-ais N     publish at most N AIS targets, the most recently seen (default 500)
  --claim         send an ISO address claim on the CAN bus (experimental, off by default)
  --no-claim      do not send an address claim (the default; accepted for compatibility)
  --help          show this help
  --version       show the version
```

Replay example:

```bash
build/n2kd/n2kd --replay n2kd/tests/fixtures/garmin-airmar.log --speed 5 --stdout
```

Behavior:

- Snapshots go out at `--hz`: a `vessel` snapshot every tick, then an `ais` snapshot when targets exist and either their content (ignoring `t` and per-target `age` and `posAge`) changed since the last one sent, a new client connected, or 10 s have passed since the last one; plus one empty-targets `ais` snapshot when the last target expires. Socket clients first receive a `hello` line; `--stdout` prints snapshots only, one JSON object per line.
- Live ticks are scheduled on the monotonic clock, so wall clock steps do not pause publishing; snapshots carry wall time. In replay mode the clock is the timestamp of the last frame read, so freshness and ticks follow the log, not the wall clock. A gap between two frames never sleeps more than 5 s of wall time (logged once), and timestamps after 2096 (above 4e9) count as unparseable lines. A final snapshot is printed at end of file, then n2kd exits 0.
- Each vessel quantity group (position with satellites, COG/SOG, heading, depth, STW, water temperature, GNSS time, RPM) is locked to the first source address seen. Other sources are ignored until that source has been silent for longer than the group's staleness window (below), then the next message from any source takes over. Silent means no message with an available primary value for the group (for depth only `depth` counts, not the offset; for heading only `heading`, not variation), so a device that only reports "not available" loses the lock. Depth and `depthOffset` always come from the same 128267 message.
- AIS reports from our own transponder (transceiver information 2, 3 or 4: own VDL transmission, own information not broadcast) are ignored.
- With `--can`, if the interface cannot be opened n2kd logs once and retries every 5 s while still serving clients. By default n2kd is a listen-only node and never transmits. Address claiming is experimental and off by default: with `--claim` it sends one ISO address claim (PGN 60928, fixed unique number) from the null address after opening, with no arbitration and no reply to ISO Request. A later plan implements proper claiming and arbitration from a non-null address.
- With `--rawlog DIR` raw frames are written to `n2k-NNNNNN-YYYYMMDD-HHMMSS.log` files in candump `-L` format, rotated at 50 MB; the 20 newest files are kept (about 1 GB), older ones are deleted.
- If the socket's parent directory is missing it is created.
- Exit codes: 0 clean stop (SIGTERM/SIGINT) or end of replay; 1 bad options, unopenable replay file or socket; 2 unreadable or unparsable `canboat.json`.

PGNs used: 126992 (system time), 127250 (heading, variation), 127258 (magnetic variation), 127488 (engine speed, instance 0), 128259 (speed through water), 128267 (depth), 129025 (position rapid update), 129026 (COG/SOG), 129029 (GNSS position, time, satellites), 130310, 130311 and 130316 (water temperature), and AIS 129038, 129039 (class A and B position), 129794 (class A static), 129809 and 129810 (class B static).

`cmake --install build` installs `bin/n2kd`, `share/cheekymarine/canboat.json`, `lib/systemd/system/n2kd.service` and `lib/sysusers.d/cheekymarine.conf` under `CMAKE_INSTALL_PREFIX` (default `/usr/local`; configure with `-DCMAKE_INSTALL_PREFIX=/usr` to match the release tarballs). The unit is generated at configure time so its `ExecStart` points at the installed binary. The default `--pgns` is the installed `canboat.json`; builds with `-DN2K_SOURCE_PGNS_FALLBACK=ON` (the default) also fall back to the source tree copy, release builds turn it off.

The unit runs n2kd as user and group `cheekymarine` (created by `systemd-sysusers` from `cheekymarine.conf`), so the socket `/run/cheekymarine/n2k.sock` is owned by that group with mode 0660. Add the plotter's user to the group so it can open the socket: `sudo usermod -aG cheekymarine APPUSER`. The image plan does this for you.

## JSON messages

Each message is one JSON object per line. Socket clients first receive `{"type":"hello","schema":1,"version":"X.Y.Z"}`.

Vessel snapshot (every tick):

```json
{"type":"vessel","t":1700000000.5,
 "pos":{"lat":47.6062,"lon":-122.3321},"sog":3.29,"cog":3.735,"hdg":3.6739,"hdgRef":"Magnetic","variation":0.2618,
 "depth":14.42,"depthOffset":-0.3,"stw":null,"waterTemp":287.65,"gnssTime":null,"sats":null,"rpm":null}
```

AIS snapshot:

```json
{"type":"ais","t":1700000000.5,"targets":[{"mmsi":367123450,"class":"A","lat":47.7,"lon":-122.4,"sog":3.29,
 "cog":3.735,"hdg":3.6739,"name":null,"callsign":null,"shipType":null,"navStatus":0,"age":2.5,"posAge":2.5}]}
```

Units are the NMEA 2000 SI units canboat reports: `t` and `gnssTime` epoch seconds, `lat`/`lon` degrees, `sog` and `stw` m/s, `cog` (true), `hdg` and `variation` radians, `depth` and `depthOffset` meters (`depthOffset` positive to the waterline, negative to the keel), `waterTemp` kelvin, `rpm` revolutions per minute, `sats` a count. `hdgRef` is `"True"` or `"Magnetic"`; a heading whose reference is anything else is not published. `variation` is the magnetic variation, east positive (true = magnetic + variation), from 127250 when it carries one, else from 127258. In AIS targets, `class` is `"A"` or `"B"`, `shipType` and `navStatus` are the AIS codes, `age` is seconds since any message from the target, and `posAge` is seconds since the last position report with a valid latitude and longitude (`null` if none yet). A position report that marks a field not available clears it (`null`), so `lat`/`lon` never show an old position as current.

Contract:

- Every key shown above is always present. A stale or unknown vessel value is `null`; `pos` is `null` as a whole object, never an object with null members. `hdgRef` can be `null`, and so can `navStatus` (class B reports carry none).
- Staleness windows: `pos`, `sats`, `sog`, `cog`, `hdg`, `hdgRef`, `variation`, `gnssTime`, `depth`, `depthOffset`, `stw` and `rpm` are `null` 5 s after their last update, `waterTemp` after 30 s. An AIS target is dropped 600 s after its last message.
- AIS ages are as of `t`; the daemon re-sends the AIS snapshot at least every 10 s while targets exist, so a client never sees an age frozen for longer than that.
- At most `--max-ais` targets (default 500) are published, the most recently seen ones, still sorted by `mmsi`. When more are known the message adds `"truncated":true` and `"total":N` (the number of targets known); otherwise both keys are absent.
- Order within a tick: the `vessel` line, then the `ais` line if one is sent.
- Slow clients: each client has a bounded output queue (4 MB). A client that falls further behind is disconnected; it must reconnect, and the last line it received before the disconnect may be truncated, so discard a final line without a newline.
- Schema policy: `schema` in `hello` is bumped on any key removal or type change. Added keys do not bump it; clients must ignore keys they do not know.

## Cutting a release

1. Bump `VERSION` in the `project(...)` line of the root `CMakeLists.txt` and commit. Nothing else needs editing: the version test reads the expected version from CMake.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The `Release` workflow runs on the tag: it checks the tag, runs the full CI workflow (tests, including the vcan check, and the release build), and attaches `n2kd-X.Y.Z-x86_64.tar.gz`, `n2kd-X.Y.Z-aarch64.tar.gz` and `SHA256SUMS` to a GitHub release. The same release build (`.github/workflows/build-release.yml`) runs in CI on every push and pull request, including a `--version` and replay smoke run of the aarch64 binary under qemu. Each tarball holds one top-level directory `n2kd-X.Y.Z-ARCH/` containing an install tree for prefix `/usr` (`usr/bin/n2kd`, `usr/share/cheekymarine/canboat.json`, `usr/lib/systemd/system/n2kd.service`, `usr/lib/sysusers.d/cheekymarine.conf`) plus `LICENSE`, `canboat-LICENSE`, `nlohmann_json-LICENSE.MIT`, `THIRD_PARTY_NOTICES` and an inner `SHA256SUMS` of those files. `scripts/package-n2kd.sh BUILD_DIR VERSION ARCH` builds it from a build configured with `-DCMAKE_INSTALL_PREFIX=/usr -DN2K_SOURCE_PGNS_FALLBACK=OFF`.

The tag must equal the CMake project version (`scripts/check-version-tag.sh vX.Y.Z` checks this locally), otherwise the workflow fails before building.

Platforms: the aarch64 tarball is built on Debian bookworm and needs glibc 2.36 or newer, that is 64-bit Raspberry Pi OS Bookworm or newer; libstdc++ and libgcc are linked into it statically. The x86_64 tarball is dynamically linked and needs glibc 2.38 and libstdc++ with `GLIBCXX_3.4.32` (GCC 13) or newer (Ubuntu 24.04 class).

## Installing a release

Verify the download against the release's `SHA256SUMS`, then extract only the `usr` tree onto `/` (the licenses and the inner checksums stay out of `/`):

```bash
sha256sum -c --ignore-missing SHA256SUMS
sudo tar -C / --strip-components=1 --no-overwrite-dir -xzf n2kd-X.Y.Z-aarch64.tar.gz n2kd-X.Y.Z-aarch64/usr
sudo systemd-sysusers
sudo systemctl daemon-reload
sudo systemctl enable --now n2kd
```

The installed `n2kd` finds `canboat.json` at `/usr/share/cheekymarine/canboat.json` by default. The unit reads `can0`, which must be up at the NMEA 2000 bit rate: `sudo ip link set can0 up type can bitrate 250000`. The image plan configures this automatically.
