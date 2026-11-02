# Plotter screen coordinates (window 1280x800)

Measured at 6839d19 (saved views merged; plotter code identical to afc1ffa, where the example was recorded). Every UI change can move these: confirm with a rehearsal
contact sheet or `bash x.sh shot NAME` before trusting them. The committed renders in
`docs/plotter/renders/views/*-1280x800.png` are a free map of each screen.

## Tab bar (right edge, x 1230)

| Favourites | Fav 1..n | Home | Lock | Palette |
|---|---|---|---|---|
| 3 (fresh data dir) | y 50, 145, 240 | 333 | 435 | 512 |
| 4 | y 50, 145, 240, 333 | 427 | 530 | 605 |

On a view the bar hides after 8 s, and Legend, + and - hide with it. A tap where the bar was lands
on the map instead: wake it first with a plain tap on the map or cells (e.g. 600,680), then tap.
Palette cycles auto, day, dusk, night (four taps return to the start).

## Home (3 tiles per row)

Tiles in order: views, then + New view, Tracks, Settings, About. Centres: column x 205, 590, 975;
row y 123, 347, 571. With 3 views: New 205,347; Tracks 590,347; Settings 975,347; About 205,571.
Each added view shifts the rest by one tile.

Hold a view tile (1.2 s) for its menu: Edit 398,307; Favourite 782,307; Move left 398,386;
Move right 782,386; Duplicate 398,466; Delete 782,466; Close 398,544.

## Editor (chart view)

Floating buttons: Setup 590,307; Done 590,386; Cancel 590,466. They move up when the bottom
banner is on (Done 590,347) and sit lower on a cell view (Setup 590,320; Done 590,400;
Cancel 590,478). Slots: TL 100,110; TR 1000,110; Top 590,35; Bottom 590,736; Left 35,385;
Right 1140,385; BL 40,728; BR 1135,728 (BL and BR overlap the side bars: prefer Bottom).

## Slot sheet

Opens at the bottom for upper slots, at the top for lower ones (so the slot stays in view).
Bottom-docked: On 64,486; Off 64,565; fields Depth 229,486; SOG 415,486; STW 600,486;
COG 229,565; HDG 415,565; Water temp 600,565; Position 229,644; Time 415,644; RPM 600,644;
size - 747,486; + 965,486; Done 1094,447. Top-docked: same x, y minus 400 (Done 1094,47).
Hold a slot on a live view (1.2 s) for just its sheet.

## Cell sheet (bottom-docked)

Depth 100,486; SOG 285,486; STW 470,486; COG 100,565; HDG 285,565; Water temp 470,565;
Position 100,644; Time 285,644; RPM 470,644; Done 1094,447. Tap a cell to open it.

## Setup sheet (left half)

Done 561,47; Name 323,130; Short name 323,209; icons 4 per row at x 86, 244, 402, 560,
y 326, 405, 485, 564; Chart Nav 113,683; Fish 323,683; None 534,683. Drag 320,700 to 320,250 to
scroll: then Layout 323,530; Favourite 323,646; Delete view 323,754.

## Layout gallery

7 per row, x 86, 247, 408, 569, 730, 892, 1053; rows y 144, 255, 367, 479, 591, 703.
Three columns: 247,479. Picking one closes the gallery. Close 1094,47.

## Keyboard

Helpers in engine.py: `type_text("Crab pots")`, `KEYS`, `SHIFT`, `BACK`, `KDONE`, `KCANCEL`.
Opening a field keeps its text: tap BACK once per character first.

## Other

Legend button 64,386 (bar shown); the legend sheet covers the screen: Close 1117,45.
Lock: tap Lock, then hold it 1.9 s to unlock. Start recording (Tracks page) 120,45.
