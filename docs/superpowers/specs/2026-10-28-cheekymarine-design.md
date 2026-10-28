# CheekyMarine: second helm display, design

Date: 2026-10-28
Status: reviewed by builder check, awaiting owner approval

## 1. Intent

A second 9" touch chart plotter at the helm of the owner's boat, mounted beside the existing Garmin GPSMAP 943xsv. While fishing, the owner stands at the stern and needs to read sonar, depth and speed from there. One 9" Garmin split between chart and sonar is too small to read at that distance. With two screens, the Garmin runs full-screen sonar and the new unit runs full-screen chart with large depth and speed numbers.

The owner wants to build both hardware and software, using off-the-shelf boards and parts, and wants to learn by studying existing open source marine projects (OpenCPN, SignalK, canboat, OpenPlotter, AvNav, KIP) rather than running them.

### Why not just buy a second Garmin

A new 9" plotter is $1500 to $2000. The owner wants best value for money, well under $1000, and wants to own the software.

### Why sonar is out of scope

The GT51M-TM transducer is wired directly to the 943xsv's 12-pin sonar port. The 943xsv outputs only the computed depth number (and water temperature) to NMEA 2000. The echo picture is shared only over the proprietary Garmin Marine Network (ethernet), whose sonar payload has not been publicly reverse engineered. The 943xsv has one composite video input and no video output. Garmin's phone app does not mirror the screen. Getting Garmin's sonar picture onto this display is therefore not feasible in this project. Building a separate sonar engine with a second transducer is a possible future project, not this one.

## 2. Goals

1. Chart page readable from the stern: own boat on a real nautical chart, with depth and speed large enough to read from about 12 to 15 ft away.
2. Full nautical chart content from NOAA ENC: depth areas and contours, soundings, rocks, wrecks, obstructions, buoys, beacons, lights, anchorage areas, marinas and small craft facilities, coastline. Land interior is a flat fill; land detail does not matter.
2a. Fishing chart mode (owner requirement): like Garmin's Fishing Chart. Nav clutter off, high-detail bottom contours at a fine interval, depth-shaded relief so structure, drop-offs and humps stand out. Sourced from NOAA/NCEI bathymetry, not from ENC contours, which are too coarse.
3. All live data from the existing NMEA 2000 bus: position, COG/SOG, heading if present, depth, water temperature, AIS targets.
4. Garmin-like data overlays: user picks which slots are shown (four corners, top banner, bottom banner, left or right side bar), which field goes in each slot, and the size of each.
5. Waypoints, routes, tracks, man overboard (MOB), alarms, night mode, depth history graph.
6. Behaves like an appliance: soft power button, boots straight into the app, no desktop, no keyboard, survives power cuts without corruption.
7. Chart and software updates downloaded over the owner's phone hotspot from GitHub releases.
8. Hardware bill of materials well under $1000, target $400 to $600.

## 3. Non-goals

- Sonar of any kind (no transducer, no sonar picture, no Garmin sonar mirror).
- Radar display (GMR Fantom 18 stays on the Garmin).
- Autopilot control.
- Sharing waypoints or routes with the Garmin. This unit keeps its own list.
- Canadian (CHS) charts. NOAA ENC only. US cells near the border show some Canadian water; that is all we get.
- Always-on internet. The unit is offline except when the owner joins it to a hotspot for updates.
- Submersion rating. Enclosed cabin, wet hands and spray, not a wash-down.
- wa-creel On Water layers (SSCOFS current fields, fishing-condition area polygons, tide and slack timing). Owner wants these on this display eventually. Not this project. The chart layer architecture should not make adding a raster or vector overlay from another pack hard, but no work is done for it now.

## 4. Anti-goals (what would make this a failure)

- A chart that looks like a road map. It must read like a nautical chart: depth tints, soundings, hazards, nav aids.
- Small or fiddly touch targets. Wet fingers, boat moving. Everything tappable is large.
- Ghost touches from water droplets changing the page or dropping waypoints. Touch lock is required.
- A unit that needs a keyboard, SSH, or a desktop to recover.
- Depth and speed numbers that are not readable from the stern.
- SD card corruption on power loss.

## 5. Constraints

- Boat: enclosed cabin helm. Salt air. Wet hands. Spray possible, not immersion.
- Power: 12V dash supply, noisy with main and kicker running. Expect 9 to 16V with transients. Power is switched manually, like the Garmin: press to turn on, hold to shut down. Not tied to ignition.
- Screen: 9" to 10.1" class, capacitive touch, 1000 nit class, mounted beside the 943xsv.
- Existing network: NMEA 2000 backbone with 943xsv, GPS 24xd, VHF 215 AIS, engines. Garmin Marine Network (ethernet) also present but not used by this unit.
- Waters: Puget Sound, San Juan Islands, Washington Pacific coast.
- Owner can build circuits and prefers buying modules over fabricating boards.
- Target: installed and usable for the April 2027 fishing season. Fishing is done for 2026.
- Boat is not reachable now (trailer broken). No NMEA 2000 recordings from this boat exist yet. Bus capture happens when the boat is back; until then development uses canboat sample logs and synthetic data.
- Helm space: room for a 12" class plotter beside the 943xsv and room behind the dash for Pi, HATs and regulator. Owner will supply a photo. Not a constraint on 9" vs 10.1".
- Owner has C++ and Qt experience but writes no code on this project. The assistant and its subagents write all code; the owner reviews and approves. This is a product, not a learning exercise. Stack choices are judged on capability, speed of development, readability for review, and maintainability.
- Owner runs the Garmin at maximum brightness when fishing, even on cloudy days. The display must be a high-brightness (1000 nit class) panel from the start.

## 6. Decisions made (as decided by the owner, with my reasoning where it was my call)

### 6.1 Platform: Raspberry Pi 5 (my call, owner accepted the Pi direction)

Pi 5, 8 GB. Reasons: GPIO for power button, buzzer and backlight control; CAN HAT with NMEA 2000 connector exists; large marine Pi community (OpenPlotter) to learn from; GPU drives a 1024x600 or 1280x800 panel with headroom.

Storage: NVMe SSD on a Pi 5 M.2 HAT or a high-endurance SD card with a read-only root filesystem. SD corruption on power loss is a known failure; the root filesystem must be read-only with a separate writable data partition, whatever the medium. Builder's call on NVMe vs SD; NVMe preferred if the HAT stack and enclosure allow it.

Alternative considered: x86 N100 mini PC with USB CAN adapter. More compute, 12V input built in, but no GPIO and no HAT ecosystem. Not chosen.

### 6.2 Software stack: C++ / Qt 6 / QML, MapLibre Native for the chart (owner decided)

- Application: C++17 or later, Qt 6 Quick (QML) UI, running on Linux with the Qt EGLFS/KMS platform plugin directly on the display, no desktop environment, no browser.
- Chart layer: MapLibre Native (C++) rendering vector tiles with GPU, embedded in the QML scene. We write the chart style (S-52-inspired nautical symbology) and generate the tiles. We do not write a renderer.
- Data daemon: separate process, also C++ (my call: one language, one CMake build, one cross-compile toolchain; the owner reviews C++ fluently), that owns the CAN interface (SocketCAN), decodes NMEA 2000 PGNs using canboat's PGN definitions, maintains current vessel state and AIS target list, and publishes to the UI over a local socket (Unix domain socket or localhost TCP, JSON or a compact binary; builder's call). Also writes the track log and data log. Separate process so a UI crash does not stop logging, and so the daemon can be tested with recorded CAN data without a display.
- Watchdog: a supervisor (systemd units with restart policies plus hardware watchdog) restarts the app or daemon if they die, and reboots if the system hangs.
- Owner wrote: "I want to write it myself with you, own app, and we should learn how and what to do from the different open source projects that already do this kind of stuff." Later clarified: the assistant writes and the owner reviews. OpenCPN, SignalK, canboat, OpenPlotter, AvNav, KIP and Freeboard-SK are study material, not dependencies, except canboat's PGN definitions (pgns.json), which we use as data.

### 6.3 Charts: NOAA ENC to vector tiles, delivered as release packs (owner decided)

- Source: NOAA ENC (S-57) cells for Puget Sound, San Juans, WA coast. Free.
- Tool "chartpack": runs on a dev machine or GitHub Actions. Downloads cells, converts with GDAL to GeoJSON or directly to MVT vector tiles (e.g. via tippecanoe or planetiler), packages as MBTiles or PMTiles plus the style, publishes as a GitHub release with a version and checksum.
- Device: downloads packs over hotspot, verifies checksum, swaps atomically, keeps previous pack for rollback.
- Content priority (from the owner): water matters, land is only an edge. Must include depth areas (DEPARE) with standard depth tints, depth contours (DEPCNT), soundings (SOUNDG), rocks (UWTROC), wrecks (WRECKS), obstructions (OBSTRN), buoys and beacons (BOY*, BCN*), lights (LIGHTS), anchorage areas (ACHARE), harbour and small craft facilities (HRBFAC, SMCFAC), coastline (COALNE), land area (LNDARE) as flat fill. Restricted areas, cables, pipelines, traffic separation schemes are desirable. Land detail (roads, buildings) is omitted.
- Fishing chart layer: chartpack also pulls NOAA/NCEI bathymetry for the region, builds fine contours and a depth-shaded relief, and ships them in the same pack. The app offers two chart modes on the chart page: Navigation (ENC, S-52 style, full nav aids) and Fishing (bathy contours and shading, hazards kept, nav aids and land detail hidden, high-contrast contour labels). Coverage is uneven: where no high-resolution survey exists, the fishing mode falls back to ENC contours and says so.
- Bathymetry sources and contour rules, carried over from the owner's wa-creel project (`~/projects/wa-creel/docs/new-features/bathymetry-research-findings.md` and `docs/superpowers/specs/2026-10-19-onwater-depth-contours-design.md`, plus `app/onwater/contours.py`):
  - Primary grid: NCEI Coastal Relief Model Vol. 8 Northwest Pacific, 2025 refresh, about 30 m (1 arc-second), covers Puget Sound, Strait and the outer WA coast. US Government data, free. Pull only our bbox via NCEI Grid Extract or THREDDS/ERDDAP.
  - Cross-check and inland detail: NCEI Puget Sound P290 30 m DEM.
  - High zoom detail (fishing mode zoom 14 and up): USGS CoNED 1 m topobathy DEM for Puget Sound. wa-creel skipped it as too big for a web overlay; for an offline device it is the thing that makes structure pop. Use it where it exists, downsampled to roughly 5 to 10 m, tiled only at high zooms. Decide after measuring pack size on one area.
  - Contour levels in feet: every 10 ft to 300, then 400, 500, 600. Thinned by zoom: majors (60, 120, 180, 300, 600) at low zoom, a base set of ten from mid zoom, 20 ft steps next, every 10 ft at high zoom. Majors drawn heavier and labeled first. With 1 m source data, add 5 ft steps at the highest zooms if they stay legible.
  - Land cells in the grid are NaN; fill with -1 m before contouring so every line closes against the shore.
  - Smooth with one Chaikin pass then Douglas-Peucker; drop lines shorter than a handful of points. wa-creel found raw marching-squares output angular at high zoom.
  - Labels in feet with no unit suffix, halo for contrast, at most one label per line per screen at mid zoom.
  - wa-creel's own 150 m working grid (`bathy_wa.npz`) is too coarse for us; go to the sources above.
  - Clip bathymetry and contours to US waters, same as wa-creel does, since Canadian coverage is not ours to publish.
- Style: S-52 color palette for day, dusk and night (S-52 defines all three). Safety contour configurable by the owner (e.g. 10 ft), rendered bold, shallow side tinted.
- Licensing (owner decided): no GPL code or assets in the repo. OpenCPN is read for understanding only; nothing is copied from it. Symbols are drawn by us, using US Chart No. 1 (public domain, US government) as the visual reference for buoys, beacons, lights, wrecks, rocks and obstructions. Start with a small set and grow it. Repo license: MIT (my call). Dependencies are all permissive or LGPL with dynamic linking: Qt 6 (LGPLv3, dynamically linked), MapLibre Native (BSD-2), canboat pgns.json (Apache-2.0), GDAL (MIT), tiling tool (BSD or MIT, builder confirms when choosing).

### 6.4 Data source: NMEA 2000 only (owner decided)

Minimum PGNs: 129025 position, 129026 COG/SOG, 129029 GNSS, 127250 heading, 128267 depth, 130310/130311/130316 temperature, 128259 speed through water if present, 129038/129039/129794 AIS class A/B position and static, 129809/129810 AIS class B static, 126992 time. Engine PGNs (127488/127489) are optional overlay fields.

Speed shown is SOG from GPS by default. The device listens only; it does not transmit on the bus except standard address claim (PGN 60928) so it is a well-behaved node.

### 6.5 User interface (owner decided the behavior, I propose the structure)

Pages, switched by a persistent edge tab bar or swipe (builder's call, big targets either way):

1. **Chart page.** Full-screen chart. Data overlay slots: TL, TR, BL, BR corners, top banner, bottom banner, left bar, right bar. Each slot on or off, each slot assigned a field (depth, SOG, STW, COG, HDG, water temp, position, time, distance/bearing to waypoint, XTE, engine RPM if present, etc.), each slot sized small/medium/large. Defaults: depth large in TL, SOG large in TR. Boat icon, heading line, COG vector, AIS targets with heading vectors, waypoints, active route, track.
2. **Big numbers page.** Depth and speed filling the screen, user-pickable fields. For reading from the stern.
3. **Depth history page** (also available as a bottom banner on the chart page). Scrolling graph of depth vs time, sliding window selectable (e.g. 2, 5, 15 minutes). Source is the N2K depth value, 1 to 2 Hz. This is not sonar.
4. **Waypoints and routes.** List, create, edit, delete. Create by long-press on chart or from current position. Route = ordered waypoints; "Go to" shows bearing, distance, XTE, ETA in overlay fields and draws the leg.
5. **Tracks.** Record on/off, interval, saved tracks list, show/hide.
6. **AIS list.** Targets sorted by CPA or range, tap to see details and center on chart.
7. **Alarms.** Low priority (owner: the Garmin already has audible alarms, and the motors are quiet enough to hear it). Visual only: full-width banner, dismiss with one big tap. Shallow depth, anchor drag (radius from drop point), AIS CPA/TCPA, waypoint arrival. No buzzer in the first build; leave a spare GPIO and a gland position so one can be added.
8. **Settings.** Units, night mode (auto by sunset or manual), overlay configuration, safety depth, WiFi join for hotspot, updates (software and charts), touch lock timeout, about.

Global controls, always reachable on every page: MOB button (one tap drops MOB waypoint, shows bearing and distance back, large, until cleared with a confirm), touch lock, brightness, page switch.

Night mode: S-52 night palette for the chart, dim red-on-black UI, backlight dimmed via PWM or the panel's DDC/CI if supported.

Touch: all primary targets at least 12 mm. Touch lock engages after a configurable idle time or on demand; unlock is a deliberate gesture (e.g. long press on a corner, 1.5 s). Rationale: wet fingers and droplets.

### 6.6 Power (owner constraint: manual power like the Garmin, noisy 12V)

- Input: 12V dash, 9 to 36V capable regulator. Input protection: inline fuse, reverse-polarity protection, TVS clamp for load dump, LC filter. Output 5.1V at 5A to the Pi. Must satisfy the Pi 5's 5A requirement (a plain 5V buck into USB-C limits the Pi to 3A for USB peripherals unless the PD negotiation or the config override is handled; builder resolves this, options include a 5.1V/5A buck wired to the Pi's 5V pins or a buck with PD).
- Soft power: a momentary button. Press from off: latch circuit turns the regulator on, Pi boots. Hold 2 s while on: Pi runs clean shutdown, then drops a GPIO that releases the latch and cuts power. Off-the-shelf module acceptable (e.g. a pushbutton power switch module with a kill input) or a small hand-built latch. Power draw when off must be near zero (microamps).
- Display powered from the same regulated rail or its own 12V to 5V/12V buck depending on panel. Panel must also be cut when off.
- No battery backup. Hard power loss must be survivable by the filesystem design, not by a UPS.

### 6.7 Enclosure and mounting

- Panel-mount the display in an off-the-shelf ABS or polycarbonate enclosure (IP65 class), gasketed, display bezel or lens sealed to the enclosure front. Electronics behind the panel inside the box. Cable glands for 12V, N2K drop cable, and nothing else.
- N2K drop: standard Micro-C (M12) male drop cable from an existing tee to the CAN HAT.
- Power button: sealed IP67 momentary pushbutton on the enclosure.
- Mounting: the Garmin sits on a bail bracket on top of a flat dash shelf, left of the wheel, with a switch panel and cavity below. Owner's helm photo (2026-10-28). Plan: enclosure on its own bail or RAM bracket on the shelf beside the Garmin, cables routed down through the shelf into the cavity. No flush cutout. Room exists for a 12" class unit, so 9" vs 10.1" is not space constrained.
- Light: the cabin is glass on all sides and the owner runs the Garmin at full brightness even on cloudy days. The Garmin is roughly 1200 nits. The panel is a 1000 nit class unit from the start. Still bench test it beside the Garmin in daylight before the enclosure is cut.

### 6.8 Updates (owner decided: GitHub releases, over phone hotspot)

- Settings page joins a WiFi network (hotspot). Update page checks GitHub releases for the software repo and the chart repo, shows what is available, downloads, verifies checksum and (software) signature, installs to an inactive slot, reboots into it, and rolls back automatically if the new slot fails to boot and report healthy. A/B slots for software; two pack slots for charts.
- Nothing else uses the network. No telemetry.

### 6.9 Development approach (owner decided)

- The assistant and its subagents write all code. The owner reviews PRs and approves. No tutorial pacing.
- Test-driven development is expected: tests written before implementation for daemon, chartpack, route math, alarm logic, update logic, and for QML view models where Qt Test reaches them.
- Every PR gets an adversarial review by the assistant and independent subagents before the owner sees it. The reviewer gets the diff and the spec, not the author's conclusions. The owner validates the review findings rather than re-reviewing the code line by line.
- Versioning from day one: semantic versioning (MAJOR.MINOR.PATCH) for the software, for chart packs, and for the on-device data schema (waypoints, routes, tracks, settings). Git tags drive releases. The app shows software version, chart pack version and bathymetry pack version on the About page and on the boot splash. The update page compares semvers to decide what is newer and refuses a pack whose schema major is unknown. Schema migrations are versioned and tested.
- Repo: CheekyMarine on GitHub. Monorepo with app, daemon, chartpack tool, image build, hardware notes.
- Daemon and chartpack are built and tested on the dev machine (WSL2 Linux) with recorded CAN logs and sample ENC cells. UI runs on the dev machine with the Qt desktop plugin at 1024x600, and on the Pi via EGLFS.
- Tests where they pay: PGN decoding against canboat test vectors, chart conversion output against known cells, alarm logic, route math (bearing, distance, XTE). UI is checked by hand on the device.
- Plan is sized for shipping an installable unit by April 2027.

## 7. Shopping list (first pass, prices are 2026 US retail estimates, verify before buying)

| Item | Suggested part | Est. | Notes |
|---|---|---|---|
| Compute | Raspberry Pi 5, 8 GB | $80 | |
| Cooling | Official active cooler | $5 | Enclosed box gets warm |
| Storage | 256 GB NVMe + Pi 5 M.2 HAT (e.g. Pimoroni NVMe Base or official M.2 HAT+) | $50 | Or 64 GB high-endurance SD, $15, with read-only root |
| NMEA 2000 interface | Copperhill PiCAN-M (without SMPS) | $90 | Micro-C connector, SocketCAN. Do not use the SMPS version to power a Pi 5. Cheaper alternative: Waveshare isolated CAN HAT ($20) plus a Micro-C field-attachable connector ($15) and hand wiring |
| N2K drop cable | Micro-C male to bare wire, 2 m | $25 | Plus a tee if the backbone has no spare, $20 |
| Display | 10.1" (or 9") IPS, 1280x800 or 1024x600, 1000 nit class, HDMI, capacitive touch | $180 to $450 | Two routes. Cheap: high-brightness bare panel plus HDMI driver board and PCAP touch from an OEM supplier (buydisplay, LEEHON, Alibaba class), $180 to $250, we mount it in our enclosure. Easy: finished industrial sunlight-readable monitor (Xenarc 892GFC class), $350 to $450, already housed. Builder prices both before ordering |
| Power regulator | Wide-input (9 to 36V) buck, 5.1V 5A, automotive grade (e.g. Pololu D36V50F5 class or an industrial DIN/potted module) | $20 to $35 | Add fuse, TVS, LC filter, about $10 |
| Soft power module | Pololu pushbutton power switch LV/HV or hand-built latch | $7 to $15 | |
| Button | IP67 momentary pushbutton, 16 or 19 mm | $8 | |
| Enclosure | ABS/PC IP65 box sized for the panel (Polycase, Hammond, Bud) | $40 to $70 | Cut opening for display |
| Mounting bracket | Bail bracket or RAM ball mount sized for the enclosure | $20 to $40 | |
| Cable glands, gasket, hardware | | $20 | |
| Misc wiring, connectors, HDMI/USB short cables | | $25 | |
| **Total** | | **$580 to $950** | OEM panel, SD card, Waveshare CAN at the low end; finished industrial monitor, NVMe, PiCAN-M at the high end. Under $1000 either way |

## 8. Risks and open technical questions (for the builder)

- MapLibre Native on Pi 5 under Qt EGLFS: needs confirming early. MapLibre Native has a Qt binding (maplibre-native-qt). Build it for aarch64, run a sample on the Pi with EGLFS/KMS, measure frame rate at 1024x600 with a real chart pack. If it does not perform, fall back to running under a minimal Wayland compositor (cage) which Qt supports, before considering any other change.
- Bathymetry coverage and size: NCEI DEMs for Puget Sound and the San Juans are good; the outer WA coast is patchier. Fine contours from a 1/3 arc-second DEM over the whole region produce large tile sets; chartpack must simplify and limit by zoom to keep a pack in the low gigabytes. Verify early with one area.
- Chart style effort: a convincing S-52-like style is real work, more so without borrowing symbols. Start with depth areas, contours, soundings, coastline, hazards, nav aids. Symbols for buoys and lights are simplified initially (shape plus color, no topmarks), drawn from US Chart No. 1.
- Pi 5 5A power via a plain 5V buck: resolve with the config override (usb_max_current_enable) or a PD-capable supply; USB load here is just the touch panel.
- Touch panel controller behavior with water drops: test with the chosen panel before cutting the enclosure.
- N2K bus load: listen-only is safe. Address claim must be correct or other devices will complain.

## 9. Left to the builder

- Daemon language (C++ or Rust), IPC format, exact process layout.
- Tile format (MBTiles vs PMTiles), zoom range, tiling tool.
- Exact Linux image tooling (Raspberry Pi OS Lite base vs Yocto/Buildroot; Pi OS Lite with overlayfs is the pragmatic start).
- A/B update mechanics (RAUC, Mender, or a hand-rolled two-partition scheme).
- Page navigation gesture vs tab bar.
- Which specific panel and enclosure, within the budget lines above.
- Implementation order. Two phases, driven by the April 2027 target and the boat being unreachable for now.

  **Phase 1, install candidate (must be on the boat in April):**
  (1) daemon decoding canboat sample logs and synthetic data; (2) chartpack producing tiles for one Puget Sound ENC cell, then adding the bathymetry layer for the same area; (3) Qt app showing that chart on the dev machine with a boat driven from recorded data; (4) overlay slots, big numbers page, and the Navigation/Fishing chart mode toggle; (5) Pi image with read-only root, display, power and soft-power bench test; (6) software and chart update over hotspot with A/B rollback (early, because once the box is sealed at the helm this is the only way in); (7) touch lock, night mode, tracks; (8) enclosure build. Step 0, as soon as the boat is back: plug the Pi and CAN HAT into the bus and record a few hours of real traffic, confirm which PGNs are present, and replay that log in development from then on.

  **Phase 2, after install, delivered over hotspot:** waypoints and routes, AIS list and targets (targets on the chart may land in phase 1 if time allows), MOB, visual alarms, depth history page.
