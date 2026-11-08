# plotter: plan 6, display design

Date: 2026-11-07
Status: approved by the owner 2026-11-07, after the builder check (three questions: night overlay colors and the fish-view legend answered by the owner, legend completeness settled as my call)
Parents: `docs/superpowers/specs/2026-10-29-plotter-design.md`, `docs/superpowers/specs/2026-10-31-plotter-views-design.md`, `docs/superpowers/specs/2026-11-05-plotter-plan4-design.md`. Everything there stands; this document only adds and changes what it names.
Mockups: `docs/superpowers/specs/2026-11-07-plotter-plan6-mockups/` (open in a browser; they were built for the brainstorm companion, so the frame CSS is missing, but the SVGs render).

Owner decisions are quoted or marked "owner". Everything else is my call, marked "my call".

## 1. Intent

The owner looked at the released plotter (cheekymarine-v0.1.0) on CapnButts next to the Garmin they use on the boat and raised six items. Four are display changes and are this design. Two are bugs and are fixed separately (section 9).

The yardstick is the owner's Garmin (a 9 inch GPSMAP class unit): a small own-boat icon that keeps its screen size at every zoom, heading and COG lines that can each be turned off, a COG line whose time can be set, and a track drawn in a color and line style the owner picks. The legend should explain every symbol on the chart, not only seabed codes.

## 2. Goals

1. A new own-boat icon modeled on the owner's boat (Hewescraft 240 Ocean Pro), about 9 mm long, fixed screen size (section 4).
2. AIS icons scaled to keep today's ratio to the boat (section 5).
3. Heading line and COG line each switchable; COG time settable 1 to 60 whole minutes; a T crossbar at the COG line's end (section 6).
4. Track color (a color picker) and line type, one display setting for every track (section 7).
5. A legend with collapsible categories covering every chart symbol, matching the current view (section 8).
6. Every overlay drawn on top of the chart uses the amber night look (section 4.1).

## 3. Non-goals

- No own-boat size setting (my call; the owner did not ask for one).
- No per-track styling. Owner: "All tracks should change based on the setting. It is a display setting."
- No "Your boat" category in the legend (owner: "Leave 1 off").
- No change to the heading line's length or look (50 km, thin solid) beyond the on/off switch.
- No change to when the COG line shows (still only above about 0.5 kn, `kMinCogSogMs`).
- No change to the AIS tap radius (8 mm, `ChartPage.qml`), so smaller AIS icons stay as easy to tap.

## 4. Own-boat icon

Source today: `plotter/src/app/Icons.cpp` `boat()`, 12 mm long, orange fill, black outline. Mockup: `boat-icon-v3.html`, style C (owner picked C).

- **Shape** (top down, bow up; coordinates in a 40 x 100 box, the mockup's): pointed bow curving out to full beam about 40% back, straight sides, square transom at 88. Main outboard (9 x 9, centered) and a smaller kicker (4.5 x 6, to starboard) behind the transom.
- **Day colors**: hull fill `#6E99BE` (owner), hull outline `#1e3448`; cabin `#d4d8dc` with `#1e3448` outline, a rounded box from 36 to 64; a dark windshield band `#22303f` across the cabin front; motors `#3a3f45` with `#111` outline.
- **Navigation lights** (owner): "like a capital D and a mirror of that D", "on the cabin near the front", about the mockup size. Port is the mirrored D, red, flat edge on the cabin's left wall, bulging outward; starboard is the D, green, on the right wall. Half-disc radius 3.5 in box units, from 37.5 to 44.5. Muted (owner): red `#b85450`, green `#4f9a64`.
- **Size**: 9 mm long on screen (my call, from the owner's Garmin photo: the Garmin boat measured about 9 mm on a 9 inch screen). Fixed screen size at every zoom, like today and like the Garmin.
- **Dusk**: the day colors darkened the way the dusk chart palette is (`_toward_black(colour, 0.45)` in `chartpack/src/chartpack/style/palette.py`) (my call).
- **Night**: amber, as in the mockup's night column (owner accepted v3 without change): hull fill `#7a5000`, outlines `#E0A000`, cabin `#2a1a08`, windshield `#0a0500`, motors `#1a0e04` with `#C08000` outline, lights red `#a02018` and green `#20A040` (the amber night palette's `LITGN`).
- The rotation rule is unchanged: heading, else COG, else 0.

### 4.1 Night overlays go amber

Today every overlay is red-only at night (no channel but red above 0x20): the `Overlays.h` comment, `overlayColours()` in `plotter/src/core/Overlays.cpp`, and the tests `nightOverlayColoursAreRedOnly` and `nightIconsAreRedOnly` in `plotter/tests/tst_palette.cpp`.

Owner (2026-11-07): all overlays go amber at night, so everything on top of the chart matches the amber chart (owner's pick of 2026-11-05). That is the boat (section 4), AIS icons and vectors, heading line, COG line and its T, and tracks (section 7). The red-only overlay rule is replaced by an amber rule: night overlay colors stay within the amber night palette's range (dim reds, ambers up to about `#E0A000`, and the dim green `#20A040` only for the starboard light). The two tests are rewritten to that rule, not deleted. Exact amber values for AIS, heading and COG are the builder's, within that range.

A charts pack built with `--night red` is not the default and the plotter cannot tell which night variant a pack uses; overlays are amber regardless (my call). Following the pack's variant would need the pack to record it, which is out of scope.

## 5. AIS icons

Owner: "AIS targets should be proportional to the new boat icon." Mockup: `ais-scale.html` (owner: "those sizes look right").

| Icon | Today | New |
|---|---|---|
| Own boat | 12 mm | 9 mm |
| Class A | 8 mm | 6 mm |
| Class B | 6 mm | 4.5 mm |
| Lost (hollow) | 8 mm | 6 mm |

Shapes and day colors unchanged (night: section 4.1). The outline width (`max(2 px, 0.4 mm)`) stays.

## 6. Heading and COG lines

Owner: "I use both lines and I want them. I can enable or disable both on my Garmin. I can also change the COG line time. 1 minute being the minimum."

New settings (persisted like the existing ones in `Settings`):

| Setting | Values | Default |
|---|---|---|
| Heading line | on / off | on (my call) |
| COG line | on / off | on (my call) |
| COG line time | whole minutes, 1 to 60 (owner: "should just have a min and max and be an integer"; max 60, owner) | 1 min (owner: "Which is what I usually set it to") |

- Settings rows read so the meaning is clear, for example "COG line time: 1 min" (my call).
- The time picker is touch only (no keyboard on the boat): a stepper with minus and plus that repeats when held, like the slot size control in `SlotSheet.qml` (my call).
- The COG line's length becomes SOG x time (today `kCogSecs` = 120 s, fixed).
- **T end** (owner: "On the tip of that line put a T cross"): a short crossbar at right angles to the line at its far end, so the end reads as a T. Same color as the COG line, solid, about 4 mm wide on screen at every zoom (my call). Drawn only when the COG line is drawn.
- Turning a line off hides it at once, with no restart.
- Night colors: section 4.1.

## 7. Track style

Today: every track (finished and recording) is a solid line, width 2.5, palette color (`c.track`, magenta in day), from `ChartController.cpp` layers `cm-tracks-line` and `cm-track-active-line`.

Owner: dark gray, dashed by default; "probably should be able to pick the color in setting"; line type a setting too; "All tracks should change based on the setting. It is a display setting."

| Setting | Values | Default |
|---|---|---|
| Track line type | Solid, Dashed, Dotted, Dash-dot (owner: "Line types are good", `track-style.html`) | Dashed |
| Track color | any color, from a color picker (owner: "Colors should just be a color picker") | dark gray `#444444` (my call for "dark gray") |

- **Color picker**: touch only, no keyboard. Its form is left to the builder, with these limits: big touch targets (at least the app's existing button size), a preview line in the chosen color and line type, and a way back to the default (my call).
- **Width**: 2.5, unchanged.
- **Dusk**: the chosen color darkened like the dusk chart palette (my call).
- **Night**: the color is replaced by one dim amber and the line type is kept (owner: "Your night guess is correct"). The exact amber is the builder's; it must sit in the amber night palette's range (`TXTDP` `#C08000` or dimmer).
- The recording track and finished tracks look the same.

## 8. Legend

Today: `plotter/qml/LegendSheet.qml`, "Seabed legend", one flat list from the charts pack's `legend.json`.

Owner: "the symbols for buoys, lights, and AIS targets, rocks, any icon really. the legend should break down into categories. we already have Seabed. Each category should be collapsable so Users don't have scroll so much."

Categories, in this order:

1. **AIS targets**: Class A, Class B, lost target, course vector.
2. **Buoys and beacons**: nun, can, spherical, pillar, spar, lateral beacon, cardinal beacon, other beacon. Navaid color comes from the chart data, so each row shows the shape and a short note on what color means.
3. **Lights**: light flare.
4. **Hazards**: rock, wreck, obstruction, and the red dotted ring that marks one as dangerous at the safety depth.
5. **Depths and areas** (mockup `legend-depths.html`, owner: "I dig it"): very shallow, shallow, medium, deep (each a swatch with its range filled in from the shallow, safety and deep settings, in the user's depth unit), dries at low tide, land, no chart data, depth contour, safety contour, soundings (black at or shallower than safety depth, gray deeper), restricted-area edge with ticks, kelp.
6. **Seabed**: today's list, unchanged in content.

**Complete coverage** (my call, from the owner's "any icon really" and the builder check): every layer the nav and fish styles draw gets a legend row, including those the list above does not name: anchorage area fill, traffic separation fill, cable and pipeline lines, ferry, navigation and recommended-track lines, coastline, and the dashed outline of seabed (CMECS) areas. The builder places them in the categories above, renamed if needed (for example "Depths and areas" can become "Depths, areas and lines"). A test fails when a style layer has no legend row, so a new layer cannot slip in unexplained.

**Fish views** (owner: "Match the view"): the legend shows what the current view draws. On a fish view:

- Buoys and beacons: not shown. The fish style leaves them off on purpose (chartpack design 2026-10-28, "Nav aids are hidden; lights and hazards stay"); owner 2026-11-07: keep them off.
- Depths and areas: the fish chart's depth bands (by survey depth) instead of the four nav depth areas; minor and major contour lines; the coarser fallback contours from the ENC, meaning "no fine survey here"; the relief shading; no soundings.
- AIS targets, Lights, Hazards, Seabed: as on nav views.
- Chart symbols come from the fish sprite sheet (`pack://sprites/fish`) on fish views.

Behavior (owner: "guesses are correct"):

- Each category is a header with its row count and a chevron; a tap opens or closes it.
- All start closed; the legend remembers which were left open (persisted).
- Each row shows the real chart symbol in the current palette (day, dusk or night), so the legend matches the screen. The symbols come from the same source the map uses (the charts pack sprites for chart symbols, `chartIcons()` for AIS), not from redrawn copies (my call).
- The sheet title becomes "Legend" (my call).
- Without a charts pack, categories that need the pack's sprites show a short "Needs a charts pack" line (my call); AIS still shows.

## 9. Bugs (separate track, not designed here)

These are fixed by reproducing first, then a test, then the fix:

1. **Corner slot resize stops early.** Owner: "It seems to get stopped when nothing is blocking it", "seems to happen on all of them", "very much seem to be an issue of relative sizes". Suspect: the clamp in `ChartPage.qml` `maxMmFor()` / `PanelMath.maxSlotSizeMm()`, which uses every slot's size.
2. **Slot edit dialog buttons overlap** when editing a slot (`SlotSheet.qml`).
3. **Long press on a corner slot does not show the resize handle**, while selecting a slot in the view editor does.

## 10. Tracking

Each of sections 4 to 8 and each bug in section 9 gets a GitHub issue (owner wants the record on GitHub), referenced from the plan and the PRs.

## 11. Left to the builder

- How the T crossbar is drawn (a rotated symbol at the line's end or a short line feature), as long as it keeps its screen size.
- How heading and COG on/off are applied (layer visibility or leaving the feature out).
- The color picker's form, within section 7's limits.
- How legend rows get the pack's sprite images into QML.
- Exact count labels and row wording in the legend, within section 8.
