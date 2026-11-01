# plotter: saved views, design (addendum to the 2026-10-29 plotter design)

Date: 2026-10-31
Status: approved by the owner 2026-10-31 ("let's go with this, approved")
Parent: `docs/superpowers/specs/2026-10-29-plotter-design.md` (plan 3, merged in PR #24). This addendum supersedes parent sections 6.6 (mode toggle), 6.7 (editing, sizes), 6.8 (big numbers page), 6.9 (tabs, idle lock) and goal 7 (idle timeout) where they differ. Everything else in the parent stands.
Ledger: `.superpowers/sdd/2026-10-29-plotter/progress.md` (owner quotes dated 2026-10-31). Mockups the owner reacted to: `docs/superpowers/specs/2026-10-31-plotter-views-mockups/` (README there maps each screen to its answer).

Owner decisions are quoted or marked "owner". Everything else is my call, marked "my call".

## 1. Intent

The owner's moment: "going from navigation to fishing. I'd switch my garmin to fish finder and CheekyMarine to big numbers and fishing chart." Today that takes a mode tap plus slot edits. The owner wants named, saved layouts ("views") that are set up once at the dock and switched with one or two taps on the water, the way the Garmin chartplotter's Home, Pinned and Combination pages work. "A good, intuitive UX is really what I want" (owner).

## 2. Goals

1. Views: a named list the owner creates, edits and deletes. A view = icon + short name + name + chart (Nav, Fish, None) + its layout. Chart views (Nav, Fish) carry the eight overlay slots; a None view carries a cell grid.
2. Per-slot dynamic size: each overlay slot sized on its own, continuously, in mm of digit height, clamped to the space available (R51).
3. Favourites in the tab bar: favourite views get their own tab (icon over short name), as many as fit. One tap to switch.
4. Home page (house tab): tiles for every view, New view, Tracks, Settings, About.
5. One editor: the live view with its slots or cells outlined, a Setup sheet for the view's own properties, per-slot and per-cell sheets.
6. Cell views: a layout chosen from a gallery of every rectangular tiling of a 2x2, a 2x3 and a 3x2 grid (72 shapes, at most 6 cells; see 6.4), fields per cell, digits auto-sized to fill.
7. Remove the Navigation/Fishing mode button and the idle auto-lock; the tab bar auto-hides on views so the chart gets the whole width, any tap brings it back.
8. Three shipped views on first run: Navigation, Fishing, Big numbers.
9. Both 1024x600 and 1280x800 keep the 12 mm control floor and the 15 mm tab size; screenshots at both sizes at every checkpoint.

## 3. Non-goals

- Shortcuts beyond the favourite tabs (owner: "Short cuts would be cool, but we don't have to start there"). Hold gestures listed in section 6.9 are the only extras, and they are cheap.
- AIS density and the AIS sheet covering top slots at 1024x600: deferred until the owner has a boat recording (owner, 2026-10-31).
- Drag and drop of slots to other positions. Positions stay the eight fixed ones.
- Per-cell sizing in None views: cells auto-size (owner chose cells over free slots for None, mockup 06).
- Importing or exporting views, syncing between displays.
- Task 18 (Pi measurement) stays its own PR when the kit arrives.

## 4. Anti-goals

- Anything on the water that needs a steady finger: drag and pinch live only inside the editor (dockside). Live views keep tap-only controls.
- A tab bar that scrolls, or one that cannot be brought back with a single tap when hidden.
- A view that cannot be shown because its chart pack is missing: it must degrade, not block.
- Losing a view's settings on a bad save: the view store keeps unknown keys like the slot JSON does (R34).

## 5. Constraints

- Sizes in mm through `Units`; 12 mm control floor, 15 mm tabs, 25 mm large digits still the default for Navigation.
- Slot size clamped to the room left (R51): a slot never overflows the page or its neighbours; bars and banners still shrink the chart viewport rather than cover it.
- No GPL (owner rule): Qt Virtual Keyboard is GPL-only, so the name keyboard is our own QML. Icons from an MIT or Apache-2 set, bundled, listed in `THIRD_PARTY_NOTICES`.
- No keyboard on the boat except the on-screen one in the Setup sheet.
- Views live in the existing SQLite settings store; the schema version bumps and migration keeps today's slots and numbers settings as the Navigation and Big numbers views.
- Test rules of the parent: C++ unit tests for every model and store change, QML tests through the stub map, screenshots of every new page at both sizes.

## 6. Decisions

### 6.1 The view model (owner, with my data shape)

A view has: `id` (uuid), `name` (1 to 24 characters), `short` (1 to 6 characters, the tab label), `icon` (name from the bundled set), `chart` (`nav`, `fish`, `none`), `favourite` (bool), `order` (position among views), `slots` (the eight slot entries, each `{id, on, field, sizeMm}`), `cells` (`{layout, fields[]}`), `created`/`modified` timestamps. Both `slots` and `cells` are stored for every view (my call), so switching a view's chart between a chart and None and back in the editor keeps what was there.

`sizeMm` is a number (digit height in mm, one decimal), replacing the `size` name. Reading an old `size` of small, medium or large maps to 8, 14 and 25 mm (migration, my call). Floor 6 mm. Ceiling: whatever fits (section 6.6).

Order: the owner's Home tile order. Favourite tabs appear in the same order. New views append.

### 6.2 Chart kinds (owner)

- `nav`: the charts pack style, as the Navigation mode today.
- `fish`: the bathy pack style, as the Fishing mode today. If no bathy pack is installed (parent 6.5: Fishing needs charts and bathy of the same region), the view shows the Nav chart with a "No fishing chart installed" chip in the top centre (my call; it replaces the disabled mode button of the parent).
- `none`: no map, white (day) or the palette background; cells instead of slots.

The mode button on the chart page is removed (owner: "No mode button on Cheeky"). The `chartMode` setting goes with it; the shown view decides the mode. `ChartController::setMode` stays as the mechanism.

### 6.3 Overlay slots in chart views (owner; sizes my call within the owner's rule)

Positions as the parent: TL, TR, BL, BR, Top, Bottom, Left, Right. Each on or off, one field, one `sizeMm`. The Nav and Fish views have only these ("The Nav and Fish charts should only have corners and bars (side, top and bottom)", owner).

Digit height drives everything: label and unit scale with the digits as today (parent 6.7); a banner's height and a bar's width follow from the digit height and the field's widest formatted value, as today.

Clamp (R51, my call on the formula): the page is divided as today (corner area between the bars, zoom column in the TR/BR gap), always at the bar-shown width (section 6.5). A slot's box width is computed from the field's widest possible formatted value (for example depth "9999", SOG "99.9", position two full lines), not the current value, so a slot's digit height never changes as the numbers change; only the box width follows the text as today. A slot's allowed maximum is the largest digit height at which that box fits: the two corners of a row (TL with TR, BL with BR) share the corner area's width and must fit side by side with a 2 mm gutter, each at most the whole minus the other's current box; the two corners of a column (TL with BL, TR with BR) likewise share its height; banners at most a third of the page height; bars at most a third of the page width. The editor clamps the slot being edited against its neighbours on every change and shows the value actually applied; a stored value above the ceiling of a smaller panel is clamped at draw time, not rewritten. Worked number (builder check): two 40 mm corners in one row do not fit a 10.1 in panel at either resolution (about 225 mm of boxes against about 200 mm of corner area), the pair clamps to roughly 32 to 36 mm each.

### 6.4 Cell views (owner)

Chart `none` lays out cells, not slots. Layouts: every rectangular tiling of a 2-column x 3-row grid, of a 3-column x 2-row grid and of a 2x2 grid: 72 distinct shapes, 1 to 6 cells, generated by code, not hand-listed (owner, mockups 07 and 08, asked for every permutation of up to 2 columns and 3 rows plus the 3x2 landscape set). The builder check corrected my count: 2x3 and 3x2 give 34 each and share only the single full cell (67), and neither contains an equal four-way split, so the 2x2 grid is added (5 new shapes: the equal quad, and a half plus two quarters in four orientations) for 72 in all and an exact migration target for today's four-cell Numbers page (my call). A layout is stored by a stable key (grid plus the rectangle list, for example `2x3:0,0,2,1;0,1,1,2;1,1,1,2`), never by index into the gallery. Gallery order: by cell count, then grid (2x2, 2x3, 3x2), then key. Fields are stored in cell order (reading order: top to bottom, left to right by the cell's top-left corner); when the layout changes, fields are kept by order and the extra cells take Depth, SOG, STW, COG, Heading, Water temp in turn (my call).

Digits fill each cell as today's Numbers page: label small top-left, unit small bottom-right.

### 6.5 Tab bar (owner, mockup 02 option B)

Right edge, top to bottom: favourite view tabs (icon above short name, 15 mm square), then the house tab (Home), a 2 mm gap, Lock, palette, and the reserved brightness and MOB spaces (parent 6.9) when room allows. Commonly used or emergency items only (owner).

Favourite tabs: as many as fit at 15 mm with the fixed items, computed from the bar height (5 at both 1024x600 and 1280x800 on the 10.1 in panel; 3 and 4 once brightness and MOB occupy their spaces). Favourites beyond that are plain views: their Home tile shows "Not on tab bar (full)" under the star, and the Setup sheet's favourite toggle says the same (my call). The reserved spaces give way to favourites until brightness and MOB exist (my call; the owner saw this on mockup 02).

The current view's tab is highlighted. A non-favourite view being shown highlights the house tab (my call).

Tracks, Settings and About leave the bar: they are Home tiles.

Auto-hide (owner, mockup 12: "B, but tapping anywhere on the screen should show it"): while a view is shown, the bar slides off the right edge after a delay and the view takes the full width (no grip). A plain tap on the map or on the cells brings it back for the delay again; a tap on the bar restarts the delay. The chart's slots slide to the right edge with the bar and back out of its way when it returns, and + , - and Legend are hidden while the bar is hidden (owner, 2026-11-01, PR #27 demo feedback: "The menu bar hide/show should move the slots to the edge on hide and back out of the way on show. The +, - and legend buttons should hide when the menu bar hides."). The slots only move, their drawn sizes do not change. The view's other established buttons (owner: "except the established buttons"): Recenter, an AIS target, the "No fishing chart" chip and a held slot or cell do their own job, keep their places and leave the bar hidden. The cells of a None view widen into the strip when the bar hides and give the room back when it shows (owner, 2026-11-01, issue #35; it overrules the earlier 'stay put'); their heights do not change, the digits refit to the wider cell and never get smaller; the map runs under the strip, and under a Right bar while the bar is shown (its width never changes with the bar). Follow mode keeps the boat where it was on screen, so the map does not jump either. My calls: 8 s default; a Settings row "Hide tab bar after: Off, 5 s, 8 s, 15 s, 30 s" (Off = never hides); the bar never hides on Home, Tracks, Settings, About or in the editor; the lock overlay still anchors to the Lock button, so locking shows the bar first; the slide takes 150 ms and a tap during the slide counts as a show. The parent's "navigation button should be able to minimize" (owner, 2026-10-31) is met by this: the mode button is gone and the whole bar minimises.

### 6.6 Home page (owner, mockups 01, 02, 10)

Tiles three across (two across if the width at 1024x600 cannot give 12 mm thumbnails: builder's call), scrolling vertically. In order: every view (thumbnail, name, a star on favourites), then "+ New view", then Tracks, Settings, About.

- Tap a view tile: show that view.
- Hold a view tile (same 1.5 s hold feel as the lock? No: 0.6 s, my call, it is not a safety control): tile menu with Edit, Favourite on/off, Move left, Move right, Duplicate ("<name> 2", short name truncated to 6), Delete (confirm; the last remaining view cannot be deleted).
- Tap "+ New view": a new Nav view named "View N", short "ViewN" truncated to 6, icon the first in the set, slots all off, opens in the editor with the Setup sheet already open.
- Tap Tracks, Settings, About: those pages, unchanged. They are left by any tab.

Thumbnail: a static drawing of the layout (chart colour block with slot boxes, or the cell shape), not a live render (my call).

### 6.7 Editor (owner, mockups 04 and 05)

Entered from Home (Edit, New view) or by holding a favourite tab (section 6.9). It is the view itself, live data and live chart underneath, tab bar dimmed and inert. Three floating buttons mid-chart, 12 mm, stacked: "Setup" (gear), "Done", "Cancel" (owner saw Setup and Done; Cancel is my call for a mis-tap). Done saves the view and shows it. Cancel discards every change made since entering, including Setup sheet changes, and returns to the page the editor was entered from.

Chart kind: all eight slots outlined (off ones faint with their position name), tap a slot for the slot sheet; the tapped slot stays selected and shows a round 12 mm handle centered on its inner corner (corner slots: half over the slot's padding, half over the chart, so the unit shows behind it) or on the midpoint of its inner edge (bars, straddling the edge), with a subtle lighter-blue double-headed arrow along the resize axis (owner, 2026-11-01, issue #29): drag it and the digit height follows, live, clamped. Cell kind: cells outlined, tap one for the cell sheet.

Setup sheet (pop-out, same look as the slot sheet, owner; full height and scrolling, since its rows plus the icon grid outgrow 600 px): Name, Short name (each opens the keyboard), Icon (grid of the bundled set), Chart (Nav / Fish / None), Layout (None only, opens the layout gallery), Favourite on/off, Delete view, Done (closes the sheet only). Chart changes apply live behind the sheet.

Slot sheet (half height, owner mockup 05 option B; sits in the half of the page away from the slot): Show On/Off, Field list, Size as big + and - (12 mm, repeat while held, 0.5 mm steps, 2 mm per second while held: my call) with the mm value between them, Done.

Cell sheet: Field list, Done.

Layout gallery: 72 landscape thumbnails, at least 12 mm tall, scrolling, the current one highlighted; tap to apply and close.

Note (builder): this said 60 before the builder check; the count is 72 (see 6.4).

Keyboard: our own QML keyboard (Qt Virtual Keyboard is GPL): letters, digits, space, backspace, Done; 12 mm keys; uppercase first letter by default, a shift key. Short name capped at 6, name at 24.

The parent's "Edit overlays" settings entry and the Numbers page cell picker are removed (both live in views now).

### 6.8 Lock and palette (owner)

Idle auto-lock is removed ("I definitely wouldn't want it to lock because I haven't touched it in a while"). The Lock button and the 1.5 s hold to unlock stay. While locked, every input (touch, mouse, wheel, native pinch, keys) stops at the overlay and pulses the padlock; the unlock hold is the only interaction (owner, 2026-11-01, issue #45: 'Lock means the only option for interaction is to unlock'). The `touchLockTimeoutS` setting and its Settings row go; `TouchLock` keeps its state machine with the timeout path deleted (my call: delete, not hide).

Palette button unchanged.

### 6.9 Shortcuts (my call, owner said shortcuts can wait: builder may drop any of these if they cost more than a day)

- Hold a favourite tab 0.6 s: editor for that view.
- Hold a slot or cell on a live view 0.6 s: just its slot or cell sheet; Done saves that change to the view.

### 6.10 Startup and defaults (owner approved on mockup 10)

Boot shows the last used view (setting `lastViewId`); if missing, the first view. Shipped on first run, all favourites, in this order:

| Short | Name | Chart | Layout |
|---|---|---|---|
| Nav | Navigation | nav | TL Depth 25 mm on, TR SOG 25 mm on, the other six as the parent defaults, off |
| Fish | Fishing | fish | TL Depth 25 mm, TR SOG 25 mm, rest off (owner, after seeing true-scale frames: "25 mm is plenty", side by side; water temp not wanted) |
| Big # | Big numbers | none | layout 2 cells side by side, Depth, SOG |

Migration of a four-cell plan 3 Numbers page: the equal 2x2 quad; three cells: the 3x2 row of three.

Migration from a plan 3 database (my call): the stored `slots` JSON becomes the Navigation view's slots (sizes mapped), the stored numbers cells become the Big numbers view, `chartMode` is dropped; a Fishing view is added as above.

### 6.11 Icons (my call)

A bundled subset of Tabler Icons (MIT) as SVG (Qt Svg becomes a dependency, LGPL-3 like the rest of Qt, dynamic): house (Home tab), anchor, fish, hash (numbers), sailboat, ship, lifebuoy, map, compass, gauge, sun, moon, waves, flag, star, settings. About 16, shown 4 across in the Setup sheet. Listed in `THIRD_PARTY_NOTICES`. Drawn in the palette's text colour so night mode stays red on black.

### 6.12 Storage (my call)

New table `views` (id, order, json) in the settings database, plus `lastViewId` in settings. JSON per view as in 6.1; unknown keys kept on save (R34 rule). Pure C++ `Views` model with unit tests: CRUD, order moves, favourite count given a bar height, migration from the plan 3 keys, clamp math for slot sizes, the tiling generator (exactly 72 distinct shapes, every one a complete tiling, stable keys).

Note (builder): this said 60 before the builder check; the count is 72 (see 6.4).

### 6.13 What the chart page keeps (unchanged)

Follow, recenter, zoom buttons, legend button, AIS sheet, "No position" chip, notice line, palette styles, safety depths, tracks drawing. The chart page becomes the "chart view page" hosting whichever chart view is shown; the Numbers page becomes the "cell view page".

### 6.14 Owner checkpoints (my call, as the parent)

1. After the Views model, tab bar and Home: screenshots at both sizes with the three shipped views and five favourites.
2. After the editor: screenshots of the editor, Setup sheet, slot sheet, cell sheet, gallery and keyboard at both sizes; a short screen recording of a drag resize.
3. Final: every page at both sizes, day and night.

## 7. Risks

- Drag resize through the stub map in QML tests: the handle lives in QML over the map item, so the tests do not need the real map. Live clamp math is C++ and unit tested.
- Favourite count at 1024x600 if the panel is smaller than 10.1 in: the count formula handles it; a zero-favourite bar still has the house tab.
- The on-screen keyboard is new UI surface; keep it minimal.
- Migration of a real plan 3 database: tested with a fixture written by the plan 3 code.

## 8. Left to the builder

- Exact thumbnail drawing on Home tiles and the gallery.
- Hold durations, step speed of + and -, the exact clamp fractions in 6.3 (within the rule: slots never overlap or leave the page).
- Where the "Not on tab bar (full)" note goes on the tile.
- Whether Home tiles are two or three across at 1024x600.
- Order of tasks; suggested: Views model and migration, tiling generator, tab bar and Home, chart view page hosting a view, cell view page, editor and sheets, keyboard, icons, settings cleanup, docs and renders.
