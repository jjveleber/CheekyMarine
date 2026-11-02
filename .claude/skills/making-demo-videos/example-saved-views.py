"""Whole-app tour of saved views (recorded 2026-11-01 at afc1ffa, 3:56). Run:
    ~/.cache/cheekymarine/demo-venv/bin/python engine.py example-saved-views.py rehearse
Coordinates: screens.md. Starts on a fresh data dir: Nav, Fish and Big # are the favourites."""
from engine import tap, hold, drag, move, wait, type_text, BACK, KDONE

TITLE = "saved-views-demo"
LAUNCH_ARGS = ["--palette", "day"]

NAV, FISH, BIG = (1230, 50), (1230, 145), (1230, 240)
HOME3, LOCK3, PAL3 = (1230, 333), (1230, 435), (1230, 512)        # three favourites
HOME4, LOCK4, PAL4 = (1230, 427), (1230, 530), (1230, 605)        # after a fourth
MAP = (600, 680)

# Each step: narration, then actions run while it plays. The step lasts the longer of the two.
STEPS = [
    ("This is the CheekyMarine chart plotter, running live on a replayed boat log from Everett toward Port Townsend. "
     "This demo covers the new saved views work.",
     lambda: wait(1)),
    ("A view is a whole screen you set up once. This is Navigation: the chart, your boat in orange, "
     "A I S traffic in green, and two big readouts, depth and speed over ground.",
     lambda: move((640, 540))),
    ("The tab bar on the right slides away after eight seconds, and the readouts and buttons move with it, so the chart gets the whole screen. "
     "[[0.5]] A tap on the chart brings it all back.",
     lambda: (wait(4), tap(MAP))),
    ("The tabs are your favourite views. Fishing uses the bathymetry chart, for bottom contours.",
     lambda: (wait(1.5), tap(FISH))),
    ("Big numbers has no chart at all. Just large readouts in a grid.",
     lambda: (wait(0.5), tap(BIG))),
    ("Back to Navigation. The Legend button explains the seabed colours.",
     lambda: (tap(NAV, 1.5), tap((64, 386), 4.5), tap((1117, 45), 0.8))),
    ("The house tab opens Home. Every view gets a tile with a small drawing of its layout, "
     "and a star marks the favourites that sit on the tab bar.",
     lambda: (tap(MAP, 0.6), tap(HOME3))),
    ("Hold a tile for its menu: edit, favourite, move it left or right, duplicate, or delete.",
     lambda: (wait(0.5), hold((205, 123)), wait(3.5), tap((398, 544)))),
    ("Let's edit Navigation. The view stays live underneath, and every slot it can hold is outlined: "
     "four corners, top and bottom banners, and side bars.",
     lambda: (hold((205, 123)), tap((398, 307), 1.0))),
    ("Tap a slot to set it up. The bottom banner is off. [[0.5]] Its sheet opens at the top, so the slot stays in view. Turn it on, and pick course over ground.",
     lambda: (tap((590, 736), 2.5), tap((64, 86), 1.2), tap((229, 165), 1.0))),
    ("Size is the digit height in millimetres. Plus and minus step it, and the editor stops it before it would "
     "run into a neighbour.",
     lambda: (tap((965, 86), 0.7), tap((965, 86), 0.7), tap((965, 86), 0.7), tap((965, 86), 0.7), wait(1),
              tap((1094, 47), 1.0))),
    ("Done saves it. [[0.5]] Course over ground now runs along the bottom.",
     lambda: (tap((590, 347), 1.5), move((640, 400)))),
    ("You don't need the editor for a quick change. Hold any readout on a live view, and you get just that "
     "slot's settings. Here the speed readout goes to speed through water, then back.",
     lambda: (hold((1000, 110)), tap((600, 486), 1.5), tap((415, 486), 1.0), tap((1094, 447), 0.8))),
    ("Now a brand new view. Home, then New view. Setup opens first.",
     lambda: (tap(MAP, 0.6), tap((1230, 333), 1.0), tap((205, 347), 1.5))),
    ("Names are typed on the plotter's own keyboard, built for touch. Call it Crab pots, and Crab for short, which is the tab label.",
     lambda: (tap((323, 130), 1.0), *[tap(BACK, 0.25) for _ in range(6)], type_text("Crab pots"), wait(0.6),
              tap(KDONE, 0.8), tap((323, 209), 1.0), *[tap(BACK, 0.25) for _ in range(5)], type_text("Crab"),
              wait(0.4), tap(KDONE, 0.8))),
    ("Pick an icon. [[0.5]] For the chart, choose none, which makes it a cell view.",
     lambda: (tap((402, 326), 1.0), tap((534, 683), 1.0), drag((320, 700), (320, 250)))),
    ("The layout gallery shows every way to split the screen into one to six cells. "
     "Seventy two of them. Take three columns.",
     lambda: (tap((323, 530), 3.5), tap((247, 479), 1.0))),
    ("Make it a favourite, so it gets a tab, and close Setup.",
     lambda: (tap((323, 646), 1.0), tap((561, 47), 1.0))),
    ("Tap a cell to choose its reading. This one becomes course over ground. Then Done.",
     lambda: (tap((980, 600), 1.2), tap((100, 565), 1.0), tap((1094, 447), 1.0), tap((590, 386), 1.0))),
    ("Crab now has its own tab. [[0.5]] The tab bar fits five favourites on this ten inch screen.",
     lambda: wait(1)),
    ("Cancel is safe. Edit this view, switch the chart to Fish, [[0.5]] then cancel, and nothing changed.",
     lambda: (tap((590, 600), 0.6), hold((1230, 333), 1.2, 1.0), tap((590, 320), 1.2), tap((323, 683), 1.5),
              tap((561, 47), 1.0), tap((590, 478), 1.0))),
    ("The palette button cycles day, dusk and night for the helm after dark.",
     lambda: (tap((590, 600), 0.6), tap(NAV, 1.0), tap(MAP, 0.6), tap(PAL4, 2.2), tap(PAL4, 2.2), tap(PAL4, 2.2),
              tap(PAL4, 1.0))),
    ("Lock stops spray and elbows from changing anything. [[0.5]] To unlock, hold the padlock for a second and a half.",
     lambda: (tap(MAP, 0.6), tap(LOCK4, 2.0), tap(MAP, 1.0), hold(LOCK4, 1.9, 1.0))),
    ("Home also has Tracks, to record where you've been, Settings, and About.",
     lambda: (tap(MAP, 0.6), tap(HOME4, 1.5), tap((975, 347), 3.0), tap(HOME4, 0.8), tap((205, 571), 3.0),
              tap(HOME4, 0.8), tap((590, 571), 3.0))),
    ("Settings holds units, depth alarms, the palette, how long the tab bar waits before it hides, and whether the chart notice shows.",
     lambda: (tap(HOME4, 0.8), tap((205, 571), 1.0))),
    ("Last thing. The plotter remembers the view you were on. [[0.5]] Here's a restart.",
     lambda: (tap(HOME4, 0.8), tap((1230, 333), 1.5))),
]
AFTER_RESTART = [("It comes back on Crab pots, with everything you set up. [[0.5]] That's saved views.",
           lambda: wait(2))]
