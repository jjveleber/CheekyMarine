# DIY helm display: component buyer specs

What each part of the main-helm Pi unit must do, so any product can be judged against it. These are requirements, not product picks. Each section ends with the part we already found, labeled **reference, not a requirement**, with the price and the date it was read. Nothing has been bought yet (decision to build: 2026-10-30). Written 2026-10-31, revised the same day after review on PR #25 and the owner's power and heat decisions.

How to read each section:

- **Job**: what the part does and what it connects to.
- **Must have**: the numbers a product has to meet, and where to find each one on a product page or datasheet.
- **Nice to have**: worth paying a little more for.
- **Disqualifiers**: walk away, and why.
- **Fits with**: limits set by the other parts.

If a product page doesn't state a must-have number, treat it as missing. Ask the seller or move on.

Owner rules this revision follows (2026-10-31):

- **Clean shutdown when the boat's main battery switch goes off is mandatory.** It must never corrupt the SSD. The unit runs from the house battery's standby (unswitched) power and watches a sense wire from the switched side (part 4).
- **Once shut down, the unit disconnects from standby power completely,** so it can't drain the battery. A relay opens; nothing in the box draws current.
- **Soft power is a nice-to-have.** A plain latching on/off switch is fine (part 3).
- **Heat has to get out of the sealed box,** through a finned aluminum heat sink in the back wall (option A). See part 20.

## How it all connects

```
 BOAT BATTERY ---- main battery switch ---- switched 12 V (helm panel)
   |  (battery side: standby power)                |
 [1] FUSE 7.5 A, at the source                   [4b] sense fuse 1 A
   |                                               |
   |   standby +, sense, negative: one 3-conductor cable [19]
   |                                               |
 ==|=== gland G1 ================= ENCLOSURE [16] =|=======================
   |                                               |       [20] heat sink
 [4d] RELAY  <------- coil -----------+          [3] UNIT ON/OFF SWITCH
   |  (open = nothing draws           |            |       (in the sense wire)
   |   from the battery)              |          [4b] SENSE TVS + INPUT (opto)
   |                                  |            |
   +--[2] TVS across + and -        [4c] CONTROLLER  <-- powered by the sense
   |                                  |   ^             wire or the relay output
   |              power going away ---+   | halted
   |                                  v   |
   +------------------------------------+  (Pi GPIOs)
   |                                    |
 [5] BUCK 12 V to 5.0-5.3 V, 5 A      [6] DISPLAY POWER: 30 V-safe input
   |                                      or its own regulator
   |  [7] USB-C power lead              |
   v                                    v
 [8] RASPBERRY PI 5, 8 GB  ---[14] micro-HDMI--->  [13] DISPLAY 9 to 10.1 in
   |   + [9] Active Cooler  <---[15] USB (touch)---     1000+ nit, touch
   |
   +-- PCIe ribbon --> [10] NVMe adapter + SSD   (under the Pi)
   +-- card slot ----> microSD recovery card   (normally in a drawer)
   +-- 40-pin header -> [11] ISOLATED CAN HAT
                            |  CAN_H, CAN_L, isolated GND
 ========================== | ==== gland G2 ==============================
                            |
                       [12] N2K DROP CABLE, Micro-C male, 1 m
                            |
                       free tee on the existing NMEA 2000 backbone
```

Mount [17] holds the enclosure [16] on the dash shelf. Glands [18] seal the two cable entries. Wire [19] covers the feed cable and everything inside the box.

Order of the power path matters: fuse at the source (protects the cable), then the relay (open when off, so nothing draws from the battery), then the TVS, then the buck for the Pi and the display's own feed. The on/off switch only carries the sense signal.

What happens when the main battery switch (or the unit's own switch) goes off: the Pi gets 2 s of grace for an engine-start dip, then shuts down cleanly on standby power, and the controller opens the relay: from then on the unit draws nothing. When the switch comes back on, the sense wire powers the controller, which closes the relay and the unit starts. Part 4 has the details.

## At a glance

| # | Part | The one number that matters most | Reference price |
|---|---|---|---|
| 1 | Fuse + holder | 7.5 A blade fuse, sealed holder for 16 AWG | $4.58 (5 A bench fuse) |
| 2 | TVS diode | Unidirectional, 15 to 18 V standoff, clamp 30 V or less | $1.06 |
| 3 | Unit on/off switch | Latching, sealed, reliable at 5 mA, rated 1 A (sense wire only) | not priced |
| 4 | Standby power + shutdown controller | Standby feed, sense input, controller, relay that opens fully when off | not priced |
| 5 | Buck regulator | 5 A continuous at 5.0 to 5.3 V, survives 30 V in | $47.95 |
| 6 | Display power | Display safe to 30 V, or its own regulator | $0 if built in |
| 7 | USB-C power lead | 20 AWG or heavier, 1 ft or shorter | $7.99 (2-pack) |
| 8 | Raspberry Pi 5 | 8 GB | $175.00 |
| 9 | Cooler | Fits under the CAN HAT (13.7 mm tall reference) | $5.00 |
| 10 | NVMe adapter + SSD | Mounts under the Pi; SSD on a Pi 5 tested list | $29.99 + $49.66 |
| 10b | microSD | A2, 16 to 64 GB | $31.99 |
| 11 | N2K interface | Galvanically isolated, SocketCAN on Pi 5 | $34.99 |
| 12 | N2K drop cable | Micro-C male, 1 m, shielded | $23.95 |
| 13 | Display | 1000 cd/m2 or more, USB HID touch, turns on by itself | $147.95 |
| 14 | Video cable | micro-HDMI to the display's HDMI type, 1 ft | $12.99 |
| 15 | Touch cable | USB-A to the display's touch port, data wires | often in the display box |
| 16 | Enclosure | IP65 or better, UV stable, 75 mm or more inside depth | $63.22 |
| 17 | Mount | Holds about 2 kg on a dash shelf, no suction | $64.49 |
| 18 | Glands | IP68, clamp range fits each cable | $1.92 (2) |
| 19 | Wire | Tinned marine 3-conductor feed, 16, 14 or 12 AWG by length | $21.93 |
| 20 | Heat sink | 1.5 °C/W or better, natural convection, anodized | not priced |

## Power budget

The numbers every power part below is sized from.

| Load | Voltage | Worst case | Source |
|---|---|---|---|
| Pi 5 with SSD, CAN HAT, touch | 5.3 V | 5 A (26.5 W) | Raspberry Pi's 5 V 5 A supply rating |
| Same, seen at 12 V through an 88% buck | 12 V | about 2.5 A | 26.5 W / 0.88 / 12 V |
| Display, reference panel at 1000 nit | 12 V | 0.65 A | 4D datasheet, 10.1" 1280x800 table |
| **Whole unit** | 12 V | **about 3.2 A** | |
| **Whole unit, battery sagging to 10.5 V** | 10.5 V | **about 3.6 A** | |
| **Unit off, main switch on or off** | 12 V | **zero** | relay open; TVS, buck and display sit after it, and the controller is powered only from the sense wire or the relay output (part 4). Soft power (part 3) would add a few mA from the switched side while the boat is on |

Typical draw while charting is well below this; the worst case is what the fuse, relay, buck and wire must carry. With the unit off, nothing draws from the battery.

Voltage drop on the feed: 16 AWG copper is about 4 milliohms per foot. A 3 ft run is 6 ft out and back, so 0.024 ohm at 3.6 A drops about 0.09 V (under 1%). If the standby feed has to come from the battery, a 20 ft run in 16 AWG drops about 0.58 V (5%); 14 AWG (about 2.5 milliohms per foot) brings it to about 0.36 V (3%); past 20 ft, 12 AWG (about 1.6 milliohms per foot) keeps it under 3%. Part 19 sets the gauge by run length.

Boat voltage the parts must live with: about 12.2 V resting, 14.4 to 14.8 V while charging, dips toward 10 V during engine cranking, and short spikes well above that. The TVS clamps spikes to about 28 V, so everything after it must survive 30 V.

Heat in the box: everything above ends up as heat inside the enclosure. In daylight at full brightness that is about 15 to 18 W: the backlight about 7.8 W, the Pi about 5 to 8 W, buck losses about 1 W, the HAT and controller under 1 W. Part 20 deals with it.

## Power

### 1. Fuse and fuse holder

**Job.** Protects the standby feed cable (part 4) if anything downstream shorts. It belongs at the power source end of the cable (the battery or the standby bus), not at the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Fuse type | Blade (ATO/ATC) so spares from the boat's kit fit | Product title or datasheet "ATO", "ATC", "blade" |
| Fuse rating | 7.5 A, 32 V DC | Printed on the fuse; datasheet "voltage rating" |
| Holder current rating | 15 A or more | Holder datasheet "rated current" |
| Holder wire size | Leads or terminals that match the feed: 16, 14 or 12 AWG (part 19) | Datasheet "wire gauge" or lead spec |
| Sealing | Cover that closes over the fuse; IP67 if it sits near the battery or in the bilge area | Product page; a cap or lid in the photo, IP rating |
| Location | Within 7 in of the source connection (ABYC E-11) | Install rule, not a product spec |

**Nice to have**

- An existing fused standby (unswitched) circuit near the helm. If there is one, it replaces the inline holder entirely.
- IP67 holder if it will hang in the open cavity below the dash.
- Tinned leads.

**Disqualifiers**

- Glass tube (AGC) holders: tube fuses crack in vibration and the boat kit won't have spares.
- Holders with leads thinner than 16 AWG: the holder lead becomes the weak point the fuse is meant to protect.
- Automotive "add-a-circuit" taps: they ride on another circuit's fuse, so a fault here kills that circuit too.

**Fits with**

- 7.5 A is 2x the 3.6 A worst case at low battery, under the 16 AWG wire's rating, and blows on a real short. The 5 A fuse in the bench cart is fine on the bench (no display) and too close to the limit on the boat.
- The holder's leads join the feed (part 19) with crimp butt connectors.
- The sense wire gets its own 1 A fuse at its switched source (part 4b).

**Reference, not a requirement.** MPD BF353 water-resistant inline ATO holder, 15 A, 16 AWG leads, $4.14, Digi-Key, 2026-10-29. Littelfuse 0287005.PXCN 5 A ATO, $0.44, Digi-Key, 2026-10-29 (bench value; the boat wants 7.5 A).

### 2. TVS diode and filtering

**Job.** Sits across + and - just after the relay (part 4d). It does nothing at normal voltage, and clamps short spikes from the alternator, pumps and the starter before they reach the buck, the display and the controller. If a big spike kills it, it fails short and blows the fuse instead of letting the spike through.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Polarity | Unidirectional | Part number ends in "A" without "CA"; datasheet "uni-directional" |
| Standoff voltage (VRWM) | 15 to 18 V: above 14.8 V charging, as low as possible above it | Datasheet "VRWM" or "reverse stand-off voltage" |
| Clamping voltage (VC) | 30 V or less at rated pulse current | Datasheet "VC" at "IPP" |
| Peak pulse power | 1500 W or more (10/1000 µs) | Datasheet "PPPM" |
| Leakage at standoff | 5 µA or less | Datasheet "IR at VRWM" |
| Package | Through-hole axial or a part that mounts on a terminal strip | Datasheet package drawing |

**Nice to have**

- An automotive load-dump rated TVS (SM8S class, 6600 W, AEC-Q101) instead of a 1500 W part. A 1500 W TVS handles switching spikes, not a full alternator load dump.
- A snap-on ferrite on the 12 V feed inside the box, plus a small LC filter (inductor plus capacitor), only if the VHF or AM radio picks up noise once installed. Don't buy until there is a symptom. (The design spec lists an LC filter as standard; this doc makes it optional, see "Departures from the design spec".)

**Disqualifiers**

- Standoff below 15 V: the TVS starts conducting while the engine is charging and cooks.
- Clamping above 30 V: every part after it is specified to survive 30 V, no more.
- MOVs (varistors) in place of a TVS: they wear out with each spike and clamp loosely.

**Fits with**

- Must be after the fuse (part 1), so a shorted TVS blows the fuse, and after the relay, so its leakage stops when the unit is off.
- Its clamp voltage sets what everything downstream must survive: 30 V for the controller's regulator, the buck, and the display.
- It doesn't protect the sense wire, which reaches the controller without passing the relay; that wire has its own TVS (part 4b).

**Reference, not a requirement.** Littelfuse 1.5KE20A: 17.1 V standoff, 27.7 V clamp, 1500 W, unidirectional, $1.06, Digi-Key, 2026-10-30.

### 3. Unit on/off switch

**Job.** Lets the owner turn the unit off while the boat stays on. It sits in the thin sense wire (part 4), not in the power feed, so turning it off looks to the controller exactly like the boat's main switch going off: the Pi shuts down cleanly, then the controller opens the relay. It carries the sense wire's current: about 5 mA for the sense input, plus the controller and relay coil (under 0.1 A in all) while it is powering them.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Action | Latching (stays where it is put): toggle, rocker, or latching pushbutton | Product title "on-off", "maintained", "latching" |
| Rating | DC rated, 12 V or more, 1 A or more | Datasheet "DC rating" |
| Low-current contacts | Reliable at about 5 mA: gold-plated contacts, or a minimum load of 5 mA or less | Datasheet "contact material", "minimum load" |
| Front sealing | IP67 (IP65 minimum) when panel-mounted, with a boot or O-ring | Datasheet "front IP rating" |
| Panel hole | 12 to 22 mm round, or a standard rocker cutout | Datasheet "mounting hole" |
| Behind-panel depth | 40 mm or less | Datasheet drawing |
| Body | Stainless steel, anodized aluminum, or UV-stable plastic | Datasheet "material" |

**Nice to have**

- Lit when on. The LED must be on the switched side, so it draws nothing when off.
- Guard, or flush mounting, so a knee or a line can't flip it.
- A spare switch on the helm's existing switch panel instead of a switch on the box. No extra hole in the box.
- **Soft power (momentary button), only if it stays simple.** The controller in part 4 can read a momentary button instead: press to turn on, hold 2 s to shut down. That needs a momentary IP67 button with gold contacts and a few lines of controller firmware, and no latch module. The catch: the controller then has to stay powered whenever the boat is on, so it draws a few milliamps from the switched side all day; with the latching switch it draws nothing.

**Disqualifiers**

- Unsealed toggles or rockers.
- Silver contacts rated only for heavy loads (a minimum load above 5 mA): at sense-wire currents they can fail to make contact.
- Lit switches whose LED draws current when off.

**Fits with**

- Wired in series with the sense wire (part 4), between the boat's switched 12 V and the controller's sense input.
- Its hole goes in the enclosure (part 16) away from where a hand rests on the display, or on the helm switch panel.

**Reference, not a requirement.** None priced yet. The first pick (EAO 82-5751.1000) was a momentary button and doesn't fit this job.

### 4. Standby power and shutdown controller

**Job.** Makes power loss safe, using the boat's own battery as the backup. The unit is powered from **standby (unswitched) power**: the battery side of the main battery switch. A thin **sense wire** from the switched side tells it whether the boat is on. When the main switch goes off, the unit is still powered, so the Pi shuts down cleanly; then the controller opens a relay and the unit is disconnected from the battery completely. When the main switch comes back on, the sense wire powers the controller, which closes the relay. Mandatory: the owner requires a clean shutdown whenever the boat's main battery switch is turned off (owner, 2026-10-31: "Finding the boat's standby power is the way to go").

What happens, step by step:

1. Main switch off (or the unit switch, part 3): the sense wire drops.
2. After 2 s with no sense (longer than an engine-start dip), the controller sets a "power going away" line to the Pi and holds it until the relay opens. It is a level, not a pulse, so a Pi that is still booting reads it when its service starts. The display stays on through the shutdown, which is fine because the battery is still connected.
3. The Pi shuts down, set to finish within about 60 s (services get a 30 s stop limit, plan 4), and signals "halted": its 3.3 V rail drops when it powers off after halt, or a GPIO goes high (which one works on the Pi 5 is a bench check).
4. The controller opens the relay. If the Pi never signals, the firmware opens it after about 3 minutes, and a hardware timer opens it after 3.5 to 6 minutes even if the controller has hung. The buck, the display and the controller itself lose power; nothing draws from the battery.
5. If the sense wire is live again (it came back during the shutdown), the controller is still powered from it: it keeps the relay open for at least 2 s, then closes it, and the Pi boots. If not, everything stays dead until the main switch comes back on.
6. If the Pi halts on its own while the boat is on (a software power-off, or after an update), the controller power-cycles it the same way, so the Pi reboots. It acts only on a change from running to halted after the Pi has been seen running (3.3 V present for at least 10 s), never on the Pi simply being off at power-up, and it gives up after 3 power-cycles in 10 minutes (then it leaves the unit off until the switch is cycled), so it can't loop. The way to turn the unit off is the switch.

It has four pieces:

**4a. Standby feed.** A fused circuit from the battery side of the main switch, to the box.

| Spec | Requirement | How to check |
|---|---|---|
| Source | Battery side of the main battery switch: an existing standby circuit near the helm, or a new run from the battery | Boat wiring diagram; meter it with the main switch off |
| Battery | The house battery (owner confirmed the boat has one). Until the diagram shows the house battery is kept apart from engine starting, assume a crank dips it | Wiring diagram |
| Fuse | At the source, within 7 in of the battery or standby bus (ABYC E-11), sized per part 1 | Install rule |
| ABYC | Check the feed against ABYC E-11's list of loads allowed ahead of the battery switch; if it isn't covered, it is a deliberate departure (recorded below) | ABYC E-11 text |
| Labels | "Always live" label at the fuse, on the cable at both ends, and inside the box: the box stays live for up to about 6 minutes after the main switch goes off | Install rule |
| Wire | Per part 19: 16 AWG up to a 10 ft run, 14 AWG for 10 to 20 ft, 12 AWG for 20 to 25 ft | Measure the run |

**4b. Sense input.** Turns the switched 12 V into a signal for the controller, with 12 V kept off its pins. The Pi never reads sense; it only gets "power going away" from the controller.

| Spec | Requirement | How to check |
|---|---|---|
| Isolation | Optocoupler (the 12 V side and the logic side share nothing but light) | Datasheet "optocoupler", "photocoupler" |
| Where it connects | On the sense wire itself, before the diode that feeds the controller. Never at the point where the two diodes join: that point is live whenever the relay is closed, and the unit would never shut down | Circuit |
| Pull-down | A resistor (about 10 kOhm) from the sense wire to negative inside the box, so an open switch reads "off" even with diode leakage | Circuit |
| Surge clamp | Its own small TVS (600 W class, 15 to 18 V standoff) where the sense wire enters the box: the main TVS sits after the relay and can't protect this wire | Datasheet, as for part 2 |
| Threshold | On above about 8 V, off below about 5 V (a resistor and a zener or a divider set this) | Circuit values; bench check with the bench supply |
| Sense current | About 5 mA into the optocoupler LED at 12 V | Resistor value |
| LED current at 30 V | Half the optocoupler LED's absolute maximum or less. With a 5 mA design point and an 8 V threshold, a plain resistor gives about 27 mA at 30 V, so a current-limiting part (constant-current diode or transistor) is required | Optocoupler datasheet "IF absolute maximum" |
| Output | To the controller only, open-collector, pulled up from the controller's own 3.3 V (the controller must read sense when the Pi is off: every cold start and every restart) | Circuit |
| Sense wire fuse | 1 A at the switched source, or tap an existing fused switched circuit | Install rule |
| Sense source | A circuit that stays live while the engine cranks (the helm panel's main feed after the battery switch). Not an ignition or accessory circuit: those drop for the whole crank, and every slow start would become a reboot | Wiring diagram |
| Sense goes to 0 V | With the main switch off, the tap reads 0 V on a meter. A device with its own unswitched feed can hold a switched bus up, and the unit would never shut down | Meter, main switch off, everything else as normal |
| Input survival | 30 V on the sense wire, behind the sense TVS | Resistor power rating at 30 V |

**4c. Controller.** A small microcontroller running the sequence above. It is powered from the sense wire (after the on/off switch) or from the relay output, through two diodes, so it is unpowered whenever the unit is off. The diode from the sense wire is a low-leakage silicon diode (not a Schottky, whose leakage rises steeply with heat and could hold a dead sense wire high). We write the firmware; it gets flashed once over USB.

| Spec | Requirement | How to check |
|---|---|---|
| Inputs | Sense (from 4b), Pi "halted" (or the Pi's 3.3 V through a divider) | Pin count: 4 or more free I/O |
| Outputs | Relay coil drive (4d), "power going away" to a Pi GPIO | Same |
| Logic levels | 3.3 V. Lines to the Pi go through series resistors (about 1 kOhm) and are driven low or released whenever the Pi's 3.3 V is absent, so they can't power a Pi that is off | Board spec; circuit |
| Power | From 12 V (sense wire or relay output, diode-ORed) through a regulator rated for 30 V | Regulator datasheet "absolute maximum" |
| Coil logic | In hardware, not firmware alone: coil on when (sense present AND the controller isn't requesting a power-cycle) OR (the controller is holding for a shutdown AND the hardware timer hasn't expired). Both controller lines have pull-downs. So a controller reset or hang never cuts the Pi while the boat is on, and can't keep the unit on the battery after it's off | Circuit; bench test |
| Relay drive | Through a transistor to the coil, with a flyback diode | Circuit |
| Watchdog | Hardware watchdog and brown-out reset enabled (with the coil logic above, a reset while the boat is on doesn't cut power) | Microcontroller datasheet |
| Hardware timer | Separate from the microcontroller: a timer or counter IC (not a long RC on an electrolytic, whose leakage can stop it firing). Reads sense from the 12 V side through its own divider, resets only while sense is present, gives a clean on/off output, and expires 3.5 to 6 minutes after sense drops across its tolerances. It can't chatter: once the contacts open with sense absent, nothing powers the coil | Circuit; bench test hangs the controller |
| Firmware rule | Hold for a shutdown only once per sense drop, and give up after about 3 minutes (always shorter than the hardware timer's 3.5-minute minimum) | Firmware review |
| Programming | USB, with a free toolchain | Product page |
| Temperature | Rated to +85 °C | Datasheet |

**4d. Relay.** Connects the standby feed to everything in the box, and disconnects it completely when the unit is off.

| Spec | Requirement | How to check |
|---|---|---|
| Type | Electromechanical, normally open (SPST-NO), non-latching, 12 V coil | Datasheet "contact form", "coil voltage" |
| Contacts | 10 A or more at 14 V DC (resistive); 16 A or more preferred for start-up surge | Datasheet "contact rating", DC |
| Coil power | 0.6 W or less (it is heat inside the box while the unit runs) | Datasheet "coil power" or coil resistance (12 V squared over ohms) |
| Must-operate voltage (closing) | Closes at a resting battery, hot: 75% of nominal or lower at 20 °C. Must-operate rises about 0.4% per °C, so 75% (9.0 V) becomes about 10.8 V at 70 °C, under the about 11.2 V the coil gets from a 12.2 V battery after the silicon sense diode and wiring (1.0 V or so). 70% or lower gives more margin | Datasheet "must operate" in % of nominal at 20 °C |
| Staying closed (cranks) | Accepted by test, not datasheet: with the box hot, dip the supply to the crank low point and check the relay holds. Datasheets don't guarantee holding below must-operate. If it fails, choose a more sensitive coil (a 9 V crank dip needs about 56% at 70 °C) | Bench crank test |
| Diodes | The diode from the relay output to the coil supply can be a Schottky (saves about 0.4 V while holding; its leakage is harmless there). The one from the sense wire stays silicon (4c) | Circuit |
| Maximum coil voltage | 15 V or more continuous at 70 °C (charging runs 14.8 V) | Datasheet "maximum continuous coil voltage" |
| Sealing | Sealed (RT III, "wash tight") or flux-proof inside the sealed box | Datasheet |
| Temperature | Rated to +70 °C or higher | Datasheet |
| Mounting | PCB pins or 6.3 mm tabs in a socket | Datasheet |

**Nice to have**

- The controller reads the battery voltage, so the app can show it.
- The controller on a small board with screw terminals.
- Relay with a built-in coil diode and an LED.
- Bench tests from the bench supply: cut the "switched" supply mid-boot, mid-run and mid-shutdown, and check the Pi always comes back; hang the controller on purpose and check the relay still opens within the hardware limit; dip the supply to the crank low point and check the relay stays closed; leave the unit switch off in a warm box (50 °C) and check the controller reads "off".

**Disqualifiers**

- Powering the unit from the switched side only: then the main switch is a hard power cut, which the owner ruled out.
- Unfused standby feeds, or a fuse at the box end: the run from the battery is unprotected.
- Anything that stays connected to the battery when the unit is off: MOSFET load switches, latch modules (the Pololu #2813 draws 0.2 µA off, and it can lose its state on dips), always-on controllers. The owner requires a complete disconnect.
- Latching (bistable) relays: they hold their last position without power, so a controller fault mid-shutdown could leave the unit connected to the battery. (A non-latching relay alone isn't enough either: it is held by the controller it powers, which is why the hardware time limit in 4c is a must-have.)
- Relays with coil power over 1 W (most 30/40 A automotive relays draw 1.5 to 2 W): extra heat in the box.
- Batteries or supercapacitors inside the box: not needed with standby power, and lithium can't be charged above about 45 °C.

**Fits with**

- Two Pi GPIOs: "power going away" in and "halted" out (or the Pi's 3.3 V rail sensed by the controller). Use pins the CAN HAT doesn't (part 11), and a "halted" pin that stays low through boot, with an external pull-down.
- Until the wiring diagram shows otherwise, assume engine starts dip the battery the unit runs on (the boat has a main engine and a kicker). The buck (part 5) must keep running down to about 7 V, and the relay must stay closed (part 4d); the 2 s sense delay keeps a crank from shutting the unit down.
- The 12 V cable into the box becomes three conductors: standby +, sense, and negative (part 19).
- The filesystem design (read-only root, A/B slots, plan 4) still matters: it covers a disconnected or dead battery, and a hung shutdown.

**Reference, not a requirement.** None chosen yet, for the relay or the controller.

Alternatives considered (2026-10-31):

- **Supercapacitor hold-up in the box** (DIY, about $40 to $60): works without standby power, but costs more, takes about 60 x 40 x 45 mm, and the cells are rated to about 65 °C. Kept only as a fallback if no standby feed can be run.
- **Geekworm UPS_Scap_5V5A** ($48.90): its wiki documents a 1 to 2 s window during shutdown where the Pi can stay off, its input stops at 24 V, and its signals reach the Pi only through contacts under the board, where the NVMe adapter goes.
- **Battery UPS boards** (Li-ion, LiFePO4, NiMH): charging is limited to about 45 °C, below the box's inside temperature.
- **Small sealed lead-acid battery**: heat-tolerant but big and heavy, and still needs this controller.

### 5. Buck regulator (12 V to 5 V)

**Job.** Turns boat 12 V into the 5 V the Pi needs, at up to 5 A, through every voltage the boat throws at it, including engine starts on the same battery.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Input range | 9 to 16 V operating, and keeps 5 V out down to about 7 V at 3 A (engine starts) | Datasheet "input voltage range", dropout or minimum input at load |
| Input survival | 30 V or more absolute maximum (the TVS clamp) | Datasheet "absolute maximum" |
| Output voltage | 5.0 to 5.3 V, fixed or adjustable into that range, 3% accuracy or better | Datasheet "output voltage" |
| Output current | 5 A continuous at 12 V input | "Maximum continuous output current" graph or table at 12 V in; ignore peak numbers |
| Temperature | Delivers that current at 60 °C ambient, or a derating curve that shows it | Datasheet derating graph |
| Topology | Switching (buck, or buck-boost) | Datasheet; efficiency spec present |
| Efficiency | 85% or better at 2 to 4 A | Efficiency graph |
| Protection | Reverse polarity (or add a diode), overcurrent, over-temperature | Feature list |
| Mounting | Holes or a tab, and terminals or pads for 16 AWG in and 20 AWG out | Photo, drawing |

**Nice to have**

- USB-C PD source that advertises 5 V 5 A. The Pi then runs its USB ports at full current without the `usb_max_current_enable=1` config line.
- Conformal coating or potting (salt air, condensation).
- Power-good output (handy for bring-up checks).
- Screw terminals.
- Made by a maker that publishes graphs, not just a headline number.

**Disqualifiers**

- Linear regulators (LM7805 class): at 12 V in and 5 A out they'd turn 35 W into heat inside a sealed box.
- Unbranded "12 V to 5 V 5 A car converter" modules with no datasheet or efficiency graph: many sag or overheat well below their label.
- USB car chargers (cigarette-lighter plugs): no clean wired input, and most can't supply 5 A at 5 V.
- Output below 5.0 V, or above 5.3 V.
- Absolute maximum input below 30 V: it wouldn't survive what the TVS lets through.

**Fits with**

- The Pi 5 flags undervoltage below about 4.63 V (a vendor-reported figure; not in Raspberry Pi's own documents). A 5.0 V buck minus about 0.1 V in the lead leaves about 4.9 V. Confirm on the bench with `vcgencmd get_throttled` (must read `throttled=0x0`).
- Output goes into the USB-C power lead (part 7), never to the GPIO 5 V pins.
- Fed from the relay (part 4d), so it is off when the unit is off.
- Its output must not feed a 5 V display rated to 5.2 V (the 4D reference is).

**Reference, not a requirement.** Pololu D42V55F5.3, $47.95, Pololu, 2026-10-29 (in the bench cart). Per its product page (read 2026-10-31): 5.3 V within 3%, input up to 60 V, reverse-voltage protection, typically 6 A at 42 V in (4 to 8 A depending on voltages, no heatsink, room temperature), 25.4 x 25.4 x 9 mm. No published temperature derating. Pololu's D36V50F5 (5.0 V), named in the design spec, also meets the voltage rule.

### 6. Display power

**Job.** Feeds the display from the relay's 12 V output (part 4d), safely across 9 to 16 V and the 30 V the TVS lets through. This is a requirement on the display (part 13) first; a separate regulator is only bought if the chosen display can't meet it. The display stays on through a shutdown and goes off with the rest of the unit.

**Must have, one of:**

- **A. 12 V input on the display** rated 9 to 16 V continuous and 30 V or more absolute maximum, both stated by the maker.
- **B. Its own regulator** for the display alone, fed from the relay output after the TVS, whenever A isn't stated:
  - 5 V displays: a second buck with 5.0 V output (not 5.3 V), rated 1.5x the display's current, 30 V input survival.
  - 12 V displays: a buck-boost (step-up/step-down) regulator with 12 V output, input 9 to 30 V or wider, rated 1.5x the display's current (about 1 A for the reference panel).
  - Either regulator: reverse-polarity protected (or behind a part that is).

**Disqualifiers**

- Powering the display from the Pi's USB ports. The Pi 5 shares 1.6 A across all four ports, and a 1000-nit panel draws more than that at 5 V (1.7 A for the reference).
- Powering a 5 V display from the Pi's 5.3 V buck when the display's maximum is under 5.3 V.
- A 12 V display wired straight to the feed when its maker doesn't state a 30 V maximum. A 16 V maximum isn't enough: clamped spikes reach about 28 V.

**Fits with**

- Fed from the relay (part 4d), so the display is off when the unit is off.
- The reference display's 12 V barrel jack is rated "12.0 V typ" with no maximum, so it needs option B unless 4D Systems confirms 30 V.

**Reference, not a requirement.** None priced yet. Likely needed with the 4D panel.

### 7. USB-C power lead (buck to Pi)

**Job.** Carries the 5 V into the Pi's USB-C power port. Using the port, not the GPIO 5 V pins, keeps the Pi's own input protection in the path. 

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Plug | USB-C male, power wires brought out to bare ends | Photo, title "pigtail", "DIY", "bare wire" |
| Wire size | 20 AWG or heavier on VBUS and GND | Product page wire gauge |
| Length | 1 ft (30 cm) or shorter | Product page |
| Current | Rated 5 A | Product page |

**Nice to have**

- Right-angle plug, to save room beside the Pi.
- Spare in the box (the reference is a 2-pack).

**Disqualifiers**

- Thin charging pigtails: at 5 A over 1 ft, 24 AWG drops about 0.26 V and 28 AWG about 0.65 V. The Pi throttles.
- Leads longer than needed: every foot adds drop.

**Reference, not a requirement.** ELNONE USB-C pigtail, 20 AWG, 6-wire, 1 ft, 2-pack, $7.99, Amazon, 2026-10-29 (in the bench cart).

## Compute and storage

### 8. Raspberry Pi 5, 8 GB

**Job.** Runs the chart app, the map rendering on its GPU, and the NMEA 2000 daemon. Everything else plugs into it.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Model | Raspberry Pi 5 | Title and photo: two micro-HDMI, PCIe connector, power button |
| Memory | 8 GB (owner's choice, headroom for future chart layers) | Title, part number SC1112 or SC1432 (both are the 8 GB board) |
| Seller | Raspberry Pi approved reseller, or the reseller's own Amazon store | raspberrypi.com product page "Buy" list |
| Operating range | 0 to 70 °C ambient (the board's own rating) | Raspberry Pi 5 product brief (October 2026 edition) |

**Nice to have**

- Buying from the same seller as the cooler (part 9) to save shipping.

**Disqualifiers**

- Kits with a wall power supply, case, or SD card: paying for parts this build replaces.
- Compute Module 5, Pi 500, Pi 4: different board, different fit. The software targets the Pi 5.
- 2 GB or 4 GB: below the owner's chosen headroom.
- Marketplace sellers with no reseller status: counterfeit and relabeled boards exist.

**Fits with**

- Board 85 x 56 mm. Its USB-C, micro-HDMI and PCIe connectors are on the edges, so the enclosure (part 16) needs room beside it for plugs and cable bends, not just above it.
- The 40-pin header carries the CAN HAT (part 11); the PCIe connector carries the NVMe adapter (part 10). The underside holds the NVMe adapter.
- 70 °C is the board's limit, and the SSD's 70 °C applies to the drive itself, which runs above the air; part 20 targets 55 °C inside the box.

**Reference, not a requirement.** Raspberry Pi 5, 8 GB, SC1112, $175.00, Digi-Key, 2026-10-29 (rechecked 2026-10-30: $175.00, in stock). Digi-Key's page shows part SC1432, the same board. Same price at CanaKit.

### 9. Cooler

**Job.** Keeps the Pi's chip below its throttling temperature. Inside a sealed box it only moves heat into the box's air; part 20 gets it out of the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Fit | Made for the Pi 5 (uses its fan connector and mounting holes) | Title "for Raspberry Pi 5" |
| Height above the board | Low enough to clear the CAN HAT's underside on its standoffs | Product drawing; reference is 13.7 mm |
| Fan control | Plugs into the Pi 5's 4-pin fan header (speed set by the Pi) | Photo of the cable and plug |

**Nice to have**

- Official part (pins and thermal pads made for the board).

**Disqualifiers**

- Enclosing cases (Argon, Flirc, aluminum heatsink cases): they cover the 40-pin header and the PCIe connector this build needs.
- Tall tower coolers: they push the CAN HAT up and the stack past the enclosure depth.
- Passive-only heatsinks: no airflow in a still box.

**Fits with**

- The CAN HAT (part 11) must sit higher than the cooler. With a 13.7 mm cooler the HAT needs standoffs of about 16 mm plus a 40-pin header extender. Check what the HAT ships with.
- The official Active Cooler is designed to stay on once fitted; plan the stack before clipping it on.

**Reference, not a requirement.** Raspberry Pi Active Cooler, SC1148, $5.00, Digi-Key, 2026-10-29 (in the bench cart). Height 13.7 mm per Raspberry Pi's product brief.

### 10. Storage: NVMe adapter, SSD, microSD

**Job.** The SSD holds the operating system, the app, chart packs and track logs, and the Pi boots from it. The adapter connects it to the Pi's PCIe port. The microSD card is only for first boot and recovery; it lives in a drawer.

**NVMe adapter: must have**

| Spec | Requirement | How to check |
|---|---|---|
| Interface | Pi 5 PCIe flat ribbon (FFC) | Title "for Raspberry Pi 5", ribbon in photo |
| Mounting | Under the Pi, leaving the 40-pin header free | Photos; "bottom mount" |
| Drive sizes | M.2 M-key, 2230 to 2280 | Product page |
| Boot | Pi 5 can boot from it | Product page or maker's docs |

**SSD: must have**

| Spec | Requirement | How to check |
|---|---|---|
| Type | M.2 NVMe, M-key (not SATA) | Title "NVMe", "PCIe"; a SATA drive says "SATA" or has B+M key notches |
| Length | 2280 or shorter (fits the adapter) | Title "2280", "2242", "2230" |
| Capacity | 128 GB minimum; 250 to 256 GB preferred at a similar price | Title |
| Pi 5 evidence | On the adapter maker's tested list, or Pi 5 owners report it booting | Adapter maker's compatibility page; forum reports with the exact model |
| Operating temperature | 0 to 70 °C | Datasheet |
| Seller | Sold by the brand, or by the retailer itself | "Sold by" line |

**microSD: must have**

| Spec | Requirement | How to check |
|---|---|---|
| Class | A2 (A1 acceptable), U3 | Logo on the card photo, title |
| Capacity | 16 to 64 GB | Title |
| Seller | Sold by the brand or the retailer itself | "Sold by" line |

**Nice to have**

- SSD with TLC flash and a published endurance (TBW) figure.
- SSD with power-loss protection or a known-good record on sudden power loss (a second layer behind the clean-shutdown design).
- SSD with low idle power; the adapter takes its power from the Pi's 5 V.
- Adapter that comes with standoffs and the ribbon.
- A spare microSD you already own (any A2 card 16 GB or more works).

**Disqualifiers**

- Top-mount M.2 HATs that cover the 40-pin header: the CAN HAT needs it, and stacking both doubles the height.
- SATA M.2 drives: the Pi 5 PCIe port can't talk to them.
- WD drives with SanDisk controllers (reports of the Pi 5 not booting), Patriot P300/P310, and look-alike "Samsung" listings from third-party sellers.
- 2280 drives on an adapter that only fits 2230/2242.

**Fits with**

- Leave PCIe at the default Gen 2. The charts don't need Gen 3, and Gen 3 is where errors show up.
- On arrival, update the bootloader, check the controller with `lspci -nn`, and soak-test booting from the SSD (repeated reboots plus a long file copy) inside the return window.
- The adapter adds height under the Pi; measure the full stack before the enclosure is drilled.

**Reference, not a requirement.**

- Pimoroni NVMe Base, PIM699, $29.99, Amazon, 2026-10-29 (in the bench cart; $19.95 at Adafruit).
- Netac NV3000 250 GB, $49.66, Amazon sold by Netac, 2026-10-29 (in the bench cart). On Pimoroni's tested list (model line). Backup: TeamGroup MP33 256 GB, $63.99.
- SanDisk Extreme 64 GB A2 microSD, $31.99, Amazon, 2026-10-29 (in the bench cart).

## NMEA 2000

### 11. NMEA 2000 interface (isolated CAN)

**Job.** Connects the Pi to the boat's NMEA 2000 bus so the app gets depth, speed, heading and AIS. It must be electrically isolated: the Pi's ground comes from the house battery wiring, the bus ground comes from wherever the bus is powered, and the two can sit at different voltages. Isolation keeps current from flowing between them through the Pi.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Isolation | Galvanic: digital isolator (or isolated transceiver) plus an isolated DC-DC for the bus side | Product page "isolated", and the schematic shows an isolator chip and an isolated power module |
| Bus | CAN 2.0B at 250 kbit/s | Product page |
| Linux driver | Shows up as a SocketCAN interface (`can0`) with a mainline kernel driver | Wiki names the driver (mcp2515, mcp251xfd); setup is a device-tree overlay, not a vendor binary |
| Pi 5 support | Listed explicitly | Product page compatibility list |
| Termination | 120 ohm terminator that can be turned off | Jumper or switch on the board |
| Bus power | Does not draw from the bus's NET-S, or draws 50 mA (1 LEN) or less | Product page; isolated side powered from the Pi |
| Form | HAT on the 40-pin header, or USB | Photo |
| Connection | Screw terminals or pins for CAN_H, CAN_L, isolated GND | Photo |

**Nice to have**

- A stated isolation voltage (1 kV or more).
- MCP2518FD controller (larger receive buffers than MCP2515), if the soak test ever shows dropped frames.
- Two channels: one loops to the other on the bench to test the daemon without a boat.
- HAT+ EEPROM (the Pi identifies the board).

**Disqualifiers**

- Not isolated. Copperhill PiCAN-M: its schematic ties the bus ground to the Pi ground. MacArthur HAT: its docs say the Pi and the bus must share one power source.
- Boards that power the Pi from the bus (PiCAN-M SMPS version): 3 A is short of the Pi 5's 5 A, and it ties the grounds.
- USB gateways that don't present SocketCAN (Actisense NGT-1, Yacht Devices USB gateway): the daemon reads SocketCAN.
- NMEA 0183 adapters: different bus.
- Boards that need the PCIe port or cover the cooler without standoffs.

**Fits with**

- Stacks on the 40-pin header above the Active Cooler: needs about 16 mm of standoff plus a header extender to clear the 13.7 mm cooler. Check what the board ships with.
- GPIOs it takes with the Waveshare wiki's default setup: SPI1 (GPIO 19, 20, 21), chip selects GPIO 16, 17, 18, interrupts GPIO 22 and 13, and GPIO 0 and 1 for its ID EEPROM. The controller's two signals (part 4) must use other pins.
- Wires to the drop cable (part 12): CAN_H to NET-H (white), CAN_L to NET-L (blue), isolated GND to NET-C (black). NET-S (red) and the shield stay unconnected. Termination off.
- The reference board also has its own 5 V / 7 to 36 V power input. Leave it unconnected on the boat: it would be a second feed into the Pi's 5 V rail. Set its logic-level jumper to 3.3 V.

**Reference, not a requirement.** Waveshare 2-CH Isolated CAN Bus HAT+, 27338 (MCP2515 + SN65HVD230, digital isolator and isolated power, 65 x 56.5 mm), $34.99, Amazon sold by Waveshare, 2026-10-29 (in the bench cart); $24.99 plus shipping at waveshare.com. Its wiki gives no isolation voltage and no standoff height. Fallback if it misbehaves on the real bus: PEAK PCAN-USB opto, about $314.

### 12. NMEA 2000 drop cable

**Job.** Connects the CAN HAT to a free port on a backbone tee. The molded Micro-C end plugs into the tee; the other end is cut and wired to the HAT inside the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Connector | Micro-C (M12, 5-pin, A-coded), male | Title "male"; pins, not sockets, in the photo |
| Length | 1 m (about 3 ft; the run is under 2 ft) | Title |
| Cable | NMEA 2000 or DeviceNet micro/light: shielded, data pair twisted | Product page "NMEA 2000 certified" or "DeviceNet" |
| Wire colors | Red NET-S, black NET-C, white NET-H, blue NET-L, bare shield | Product page, or check after cutting |
| Sealing | IP67 or better at the connector | Product page |

**Nice to have**

- NMEA 2000 certified (NMEA logo) rather than generic DeviceNet.
- Instead of cutting a cable: a panel-mount Micro-C male bulkhead connector in the enclosure plus a standard female-to-male drop. Then the box unplugs without tools. Costs a little more and needs a matching hole.
- If the backbone has no free tee port: one Micro-C T-connector (any brand; the Garmin backbone uses standard Micro-C).

**Disqualifiers**

- Female end at the tee side: wrong gender for a tee's port.
- Proprietary connectors (Raymarine SeaTalkNG, Simrad SimNet) without an adapter: don't fit the Garmin backbone.
- Unshielded or untwisted cable.
- Drops over 6 m: the NMEA 2000 limit for one drop.

**Fits with**

- Cable outside diameter sets the gland size (part 18). Measure or read it from the datasheet.
- Before buying, look at the backbone for a free tee port. If none, add a T-connector.

**Reference, not a requirement.** Ancor NMEA 2000 drop cable, 1 m, 270301, $23.95, Navstore, 2026-10-30.

## Display and cables

### 13. Display

**Job.** The screen and the touch input. It has to be readable at the helm in daylight through glass on all sides, beside a roughly 1200-nit Garmin the owner runs at full brightness.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Size | 9 to 10.1 in diagonal | Title |
| Brightness | 1000 cd/m2 (nits) or more, as a number | Datasheet "luminance" or "brightness"; "high brightness" without a number doesn't count |
| Resolution | 1024x600 minimum, 1280x800 preferred, landscape | Datasheet; check the HDMI board outputs landscape, not a rotated portrait panel |
| Panel | IPS (wide viewing angles) | Datasheet "IPS" or 85/85/85/85 viewing angles |
| Video input | HDMI (full, mini or micro), plug and play | Product page; no driver install |
| Touch | Capacitive, over USB as a standard HID multitouch device | Product page "USB touch", "driver-free", "Raspberry Pi / Linux plug and play" |
| Turns on by itself | Comes on whenever power is applied, with no button press | Manual or datasheet "auto power on"; ask the seller if not stated |
| Power | Meets part 6: 12 V input rated to 30 V, or 5 V/12 V from its own regulator | Datasheet "input voltage" with a min and max |
| Power draw | Stated at full brightness | Datasheet current table |
| Operating temperature | -10 to +60 °C or wider | Datasheet |
| Storage temperature | -20 to +70 °C or wider | Datasheet |
| Dimming | Can dim far enough for night use | OSD menu or DDC/CI brightness control |
| Mounting | Tabs, bezel or holes to fix it behind a cutout | Mechanical drawing |
| Depth | Stated; 25 mm or less | Mechanical drawing |

**Nice to have**

- Touch glass optically bonded to the LCD (less glare, no condensation gap).
- Cover-lens-bezel version: the glass is bigger than the LCD, which makes sealing it into a cutout much easier than sealing a 1:1 glass edge.
- DDC/CI brightness control over HDMI, so the app can dim the screen at night and when full brightness isn't needed. The backlight is the biggest heat source in the box.
- Anti-glare or anti-reflective glass treatment.
- Touch that ignores water drops (test before cutting the enclosure, spec section 8).
- Readable through polarized sunglasses in landscape (test).

**Disqualifiers**

- Brightness under 1000 nits, or no number given.
- Panels that wake into standby and need a button press: the button would be inside the sealed box.
- DSI, SPI or GPIO-header displays: the header is taken by the CAN HAT, and these panels are dim.
- Resistive touch, or touch that needs a vendor driver or Windows software.
- Power only over the touch USB cable from the Pi: the Pi can't supply it.
- No mechanical drawing: the enclosure cutout can't be planned.
- Finished monitors at $700 or more (Beetronics, Xenarc): they push the DIY total near $1,100 (cost comparison).

**Fits with**

- Input voltage against part 6 and the buck (part 5).
- Its HDMI connector type sets the video cable (part 14); its touch port type sets the touch cable (part 15).
- Outline plus a sealing border sets the enclosure lid size; depth plus the Pi stack sets the enclosure depth (part 16).
- If the touch port also carries power, the display draws from the Pi's USB even when it has 12 V. A USB power-blocking adapter (data only, VBUS cut) on the touch cable is required (part 15); with the 4D panel it is required regardless.

**Reference, not a requirement.** 4D Systems 4DHDMI-101-1280-800-CT-EAR-1000, $147.95, Digi-Key, 2026-10-30 (4 in stock). Per 4D's datasheet R1.3: IPS, 1280x800, 1000 cd/m2, capacitive touch glass optically bonded, metal mounting tabs, mini-HDMI (HDMI 1.4), DDC supported, one USB-C port for touch and 5 V power (4.8 to 5.2 V, 1700 mA; the datasheet says this port "parallels the power", so backfeed is likely), 12 V barrel jack (650 mA, "12.0 V typ", no maximum given), -20 to +70 °C operating, -30 to +80 °C storage. RS lists 15.98 mm depth. Its power button is on an optional button board that isn't included. Open: 12 V maximum, power-on behavior, native orientation (see open questions). Variant to price: 4DHDMI-101-1280-800-CT-CLB-1000 (cover lens bezel).

### 14. Video cable

**Job.** Pi 5 micro-HDMI port to the display's HDMI input, inside the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Pi end | Micro-HDMI (type D) male | Title, photo |
| Display end | Matches the display: full (type A), mini (type C) or micro (type D) | Display datasheet, then cable title |
| Length | 1 ft (30 cm) or shorter | Title |
| Bandwidth | HDMI 1.4 or later (1280x800 needs very little) | Title |

**Nice to have**

- Thin, flexible cable; right-angle ends if the box is tight beside the Pi.

**Disqualifiers**

- Adapter stacks (micro to full adapter plus a cable): extra joints shake loose.
- Long cables coiled inside the box: stiff, take room, pick up noise.

**Fits with**

- Plug length plus bend radius beside the Pi's long edge sets the side clearance in the enclosure.

**Reference, not a requirement.** ZeniKon micro-HDMI to mini-HDMI, 1 ft, $12.99, Amazon, 2026-10-30. The 4D display ships with a 50 cm HDMI cable, but not one with a micro-HDMI end; the bench cart's 3 ft micro-HDMI to HDMI cable isn't needed with the 4D panel.

### 15. Touch USB cable

**Job.** Carries touch data from the display to a Pi USB port.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Ends | USB-A male (Pi) to the display's touch port (USB-C or micro-B) | Display datasheet, cable title |
| Data | Data wires present | Title says "data" or "sync"; not "charge only" |
| No power | If the display's touch port also takes power: VBUS cut, by a USB power-blocking adapter (data only) or a cable without the VBUS wire | Display datasheet; adapter title "power blocker", "data only" |
| Length | 50 cm or shorter | Title |

**Nice to have**

- Right-angle ends.

**Disqualifiers**

- Charge-only cables: touch never shows up.

**Fits with**

- Use a USB 2 port (black) on the Pi.
- With the 4D panel the blocker is required: its touch port "parallels the power", so without it the panel runs from the Pi's USB (up to 1.6 A, about 8 W) and eats into the Pi's 1.6 A USB budget, which is shared with every other USB device.
- The 4D reference ships a 50 cm USB cable in the box; check its ends before buying another.

**Reference, not a requirement.** Included with the 4D display (50 cm, per 4D's datasheet).

## Housing

### 16. Enclosure

**Job.** Holds the display in its lid and all the electronics behind it, sealed against spray and rain in a glass cabin that gets direct sun.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Ingress | IP65 minimum (IP66/67 preferred), with a lid gasket | Datasheet "IP rating", "NEMA 4X" |
| Material | Polycarbonate, ABS or ASA, UV-stabilized | Datasheet "UV stabilized", "UL 746C f1" |
| Inside length and width | Display outline plus at least 15 mm per side for the sealing border | Inside dimensions on the drawing (not outside) |
| Inside depth | 75 mm or more for a 16 mm display (display plus about 45 mm Pi stack plus cable room) | Drawing; base depth plus lid depth |
| Lid | Flat enough to cut a display window and mount the panel | Drawing; a flat lid, not domed |
| Back | Flat area for the heat sink cutout (part 20) and the mount plate (part 17) | Drawing |
| Hardware | Stainless or captive lid screws | Datasheet |
| Temperature | -20 to +80 °C or wider | Datasheet |

**Nice to have**

- Light color (grey or white): absorbs less sun.
- A pressure-equalizing vent (IP67 membrane breather): keeps temperature swings from pumping moist air past the seals.
- Internal mounting bosses or an inner panel to fix the Pi stack to.

**Disqualifiers**

- No IP rating, or IP54 and below.
- Plain ABS without UV stabilization: goes brittle in sun.
- All-metal boxes: they block Wi-Fi, which the update page needs. (Option B in part 20 was not chosen.)
- Inside depth under 75 mm with a 16 mm panel.
- Dark colors in direct sun, unless nothing else fits.

**Fits with**

- Display outline (part 13), stack height (parts 8, 9, 10, 11), cable side room (part 14), switch hole (part 3), two gland holes (part 18), mount plate (part 17), heat sink (part 20).
- Measure the real Pi stack on the bench before choosing the depth.

**Reference, not a requirement.** Hammond 1554X2GY, polycarbonate, 300 x 200 x 90 mm outside, IP66/67/68, NEMA 4X, grey, $63.22, Digi-Key, 2026-10-30. Octopart lists the inside as 289.1 x 186.5 x 81.8 mm: the depth passes, and the 186.5 mm width leaves about 19 mm per side around the 148 mm tall 4D panel. Check Hammond's own drawing.

### 17. Mount

**Job.** Holds the enclosure on the flat dash shelf left of the wheel, beside the Garmin, tilted toward the helm seat.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Load | About 2.5 kg (enclosure, display, electronics, heat sink) with boat vibration | Maker's load rating for the ball size |
| Base | Screws or bolts to a flat shelf | Base plate drawing, hole pattern |
| Adjustment | Tilt and swivel, lockable | Product page |
| Materials | Marine: anodized aluminum, glass-filled composite, stainless hardware | Product page |
| Enclosure side | Plate that bolts through the box with sealed fasteners | Plate drawing and hole pattern |

**Nice to have**

- Short or medium arm: shorter shakes less.
- A second, identical ball base so the unit can move (rear helm, bench).
- The enclosure-side plate bolted to the heat sink (part 20) rather than to the plastic.

**Disqualifiers**

- Suction cups or adhesive-only bases.
- Plain steel hardware: rusts.
- Tablet clamp cradles: made for a tablet's edges, not a box.

**Fits with**

- Bolting the plate through the enclosure back needs sealing washers or gasket; it must not land on the Pi stack inside.
- Cables leave the box through glands and run down through the shelf to the cavity below (spec 6.7).

**Reference, not a requirement.** RAM Mounts RAM-101U, C-size (1.5 in) ball, double socket arm, two round plates, $64.49, RAM Mounts, 2026-10-30.

### 18. Cable glands

**Job.** Seal the two places cables enter the box: the 12 V feed and the N2K drop.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Rating | IP68 | Datasheet |
| Clamping range | Includes each cable's outside diameter | Datasheet "clamping range" (e.g. 4 to 8 mm); measure the cables |
| Thread | Matches the hole (PG or metric, with a locknut) | Datasheet thread size and hole diameter |
| Material | UV-stabilized nylon (black) or brass/stainless | Datasheet |
| Count | Two, plus a spare | |

**Nice to have**

- A bulkhead Micro-C connector for the N2K side (see part 12) instead of a gland, so the box unplugs.
- A sealed 3-pin connector (Deutsch DT class) on the feed cable for the same reason.

**Disqualifiers**

- Grey nylon without UV stabilization.
- Running two loose single wires through one round gland: it can't seal them. Use the round jacketed 3-conductor feed cable (part 19) or a multi-hole insert.

**Reference, not a requirement.** Altech 5308 509, PG9 nylon, IP68, 2 for $1.92, Digi-Key, 2026-10-30. Check its clamping range against both cables.

### 19. Wire and terminals

**Job.** The feed cable from the standby source to the box (standby +, sense, negative), and the short runs inside the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Feed conductors | Tinned copper, fine-stranded marine wire (UL 1426 boat cable or SAE J1127/J1128) | Product page "tinned", "UL 1426", "marine" |
| Feed gauge | 3% drop or less at 3.6 A: 16 AWG for a run up to 10 ft, 14 AWG for 10 to 20 ft, 12 AWG for 20 to 25 ft. The sense conductor can be the same gauge | Run length from the wiring diagram |
| Feed form | One round jacketed 3-conductor cable (standby +, sense, negative) for the gland | Product page "3-conductor", "triplex" |
| Length | Depends on where standby power is found (open question): about 3 ft at the helm, 15 to 20 ft from the battery, plus a service loop | |
| Inside the box | 22 AWG tinned for the controller signals, the switch and any switch LED | Product page |
| Terminations | Crimp terminals and adhesive-lined heat shrink | Product page "heat shrink", "marine" |

**Nice to have**

- Pre-made heat-shrink butt connectors.
- Labels on both ends of the feed.

**Disqualifiers**

- Bare (untinned) copper: corrodes inside the jacket.
- Solid-core or automotive single-strand wire: cracks in vibration.
- Solder-only joints with no strain relief: crack in vibration.

**Fits with**

- 16, 14 or 12 AWG is protected by the 7.5 A fuse (part 1) with lots of margin.
- The reference wire is single conductor; buy 3-conductor jacketed cable for the feed instead.
- Cable outside diameter sets the gland (part 18).

**Reference, not a requirement.** Ancor 16 AWG tinned primary wire, 25 ft red (182803) and 25 ft black (182003), $21.93 total, Amazon, 2026-10-30. That is single conductor; the feed needs 3-conductor jacketed cable, which seals in the gland.

### 20. Heat path and heat sink

**Job.** Gets the box's 15 to 18 W out to the cabin air, so the inside stays cool enough for the parts with the lowest ratings: the SSD (70 °C, measured on the drive), the display (70 °C), the Pi (70 °C).

**The numbers.** Target: inside air at 55 °C or less on a 40 °C cabin day. That is a 15 °C rise at 18 W, so the box must shed heat at 0.8 °C/W or better. The reference box alone (about 0.21 m2 of plastic surface) manages roughly 0.9 °C/W, a 16 °C rise before any sun lands on it. That is too close, and sun through the cabin glass makes it worse. These are rough estimates; a thermometer in the box during the bench soak settles them.

**Options. The owner chose A (2026-10-31).**

| Option | How | For | Against |
|---|---|---|---|
| **A. Heat sink in the back wall (chosen)** | Finned aluminum heat sink in a gasketed cutout in the box back. Fins outside; inside, a second set of fins or a small 5 V fan blowing the box air across the flat face. | One box. Keeps IP65 or better. Wi-Fi still gets out through the plastic. Roughly 0.6 °C/W overall, about 11 °C rise at 18 W. | A cutout and gasket to make. Heat sink must be bought to size. |
| B. Aluminum enclosure, display in a plastic or glass front | The whole box spreads and sheds heat. | Simple to seal. Best heat path of the single-box options. | Blocks Wi-Fi: needs a USB Wi-Fi adapter with an antenna outside the box. Heavier. |
| C. Filtered fan and vent | Fan pulls cabin air through filtered vents. | Moves the most heat. | Drops to about IP54. Pulls salt air across the boards. Not recommended. |
| D. Split boxes | Pi, power and controller in a second box in the shaded cavity below the shelf. Only the display (about 8 W) stays at the dash. | Best for heat: most of the load leaves the sun. | Two boxes. HDMI and USB through glands (HDMI plugs need split glands or IP67 HDMI bulkhead connectors). Video and touch cables grow past their 1 ft and 50 cm must-haves. More entries than design 6.7's "12 V, N2K drop cable, and nothing else". |

With any option: dim the backlight whenever full brightness isn't needed (the app can do it over DDC), choose a light-colored box, and keep it out of direct sun where the helm allows.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Thermal resistance | 1.5 °C/W or better in natural convection, at the length bought | Datasheet "°C/W, natural convection", or the graph of °C/W against length |
| Material | Aluminum (6063 class), anodized | Datasheet |
| Size | Fits the enclosure back with room for the gasket and the mount plate: about 200 x 150 mm or less for the reference box | Drawing |
| Fins | Run vertically as mounted (heat rises along them) | Drawing; plan the orientation |
| Base | Flat, 5 mm or thicker, drillable for stainless screws and a gasket | Drawing |
| Inside coupling | Inner fins, or a flat face plus a 40 to 60 mm 5 V fan (1 W or less) across it | Drawing; fan datasheet |

**Nice to have**

- Clear or natural anodizing: black absorbs more sun.
- The mount's ball plate (part 17) bolted to the heat sink: aluminum carries the load better than plastic.
- Double-sided (fins both faces) extrusions, so no inside fan is needed.

**Disqualifiers**

- Heat sinks rated only with forced airflow: the outside has none.
- Raw, unanodized aluminum: corrodes in salt air.
- Copper: corrodes against aluminum and stainless, and costs more.
- Peltier (thermoelectric) coolers: they draw 30 W or more and add more heat than they move.

**Fits with**

- The cutout must miss the Pi stack, the mount plate's bolts, and the lid gasket.
- Fan power comes from the 5 V side; it adds to the buck's load.
- Tested on the bench: soak with full brightness and a sun lamp or heater, thermometer inside, before the boat. Also read the SSD's own temperature (`nvme smart-log`): its 70 °C limit is the drive's temperature, not the air's, and it runs above the air.
- With passive inner fins instead of a fan, option A comes out nearer 0.65 to 0.7 °C/W: still under the 0.8 target, with a thin margin.

**Reference, not a requirement.** None priced yet.

## Fit checks across parts

Before ordering the boat parts, these have to agree with each other:

1. **Voltage chain.** Boat 9 to 16 V, spikes clamped to about 28 V by the TVS. Everything after the TVS (controller regulator, buck, display) survives 30 V or has its own regulator. The sense wire has its own TVS. The 5.0 to 5.3 V rail goes only to the Pi.
2. **Power loss.** The unit runs from the house battery's standby power; the sense wire drops when the main switch goes off; the controller gives 2 s of grace, lets the Pi shut down, opens the relay (zero draw after that), and restarts the unit whenever sense returns, including mid-shutdown. A hardware time limit opens the relay even if the controller hangs.
3. **Under the Pi.** The NVMe adapter mounts there; nothing else needs the spot.
4. **Reverse polarity.** Everything fed from 12 V either has reverse-polarity protection or sits behind a part that does (design 6.6). The buck has it; any display regulator must too.
5. **Stack height.** NVMe adapter under the Pi, Pi, Active Cooler (13.7 mm), CAN HAT on standoffs of about 16 mm. About 45 mm total (estimate; measure on the bench).
6. **Enclosure size.** Inside depth 75 mm or more; display outline plus at least 15 mm per side; room beside the Pi for the micro-HDMI and USB-C plugs; a back-wall area for the heat sink and the mount.
7. **Connector types.** Display's HDMI type matches the video cable; display's touch port matches the touch cable, with VBUS blocked; drop cable is male at the tee.
8. **GPIO budget.** CAN HAT: 0, 1, 13, 16, 17, 18, 19, 20, 21, 22. Controller: "power going away" in and "halted" out on two other pins.
9. **Current.** Fuse 7.5 A, relay contacts 10 A or more, buck 5 A, wire 16, 14 or 12 AWG, against a 3.6 A worst case at 10.5 V. Off draw zero.
10. **Heat.** 15 to 18 W out of the box at 0.8 °C/W or better (part 20).

## Departures from the design spec

This doc changes some lines of `docs/superpowers/specs/2026-10-28-cheekymarine-design.md`. The design spec gets updated to match in plan 5.

- **6.6, "No battery backup. Hard power loss must be survivable by the filesystem design, not by a UPS."** Kept: still no battery or UPS in the box. Added: the unit runs from the house battery's standby (unswitched) power, disconnects completely by relay once shut down, with a sense wire from the switched side, so turning off the main battery switch triggers a clean shutdown (owner, 2026-10-31). The filesystem design stays as the second layer. The design spec assumed power from the switched 12 V dash.
- **Soft power.** Design goal 6 ("soft power button"), 6.6's momentary button and latch, 6.7's IP67 momentary pushbutton, and section 7's "Soft power module" and "Button" rows: now a nice-to-have. A latching on/off switch in the sense wire is acceptable (owner, 2026-10-31).
- **6.6, feeding 5 V into the Pi's GPIO 5 V pins** (one option it lists): ruled out; 5 V goes in through the USB-C port to keep the Pi's input protection.
- **6.6, reverse-polarity protection.** Kept, as a fit check across the 12 V parts, covering any display regulator as well as the buck.
- **6.7, "cable glands for 12V, N2K drop cable, and nothing else."** Still true for options A to C in part 20; option D would add more.
- **ABYC E-11, connections ahead of the battery switch.** The standby feed is one. If E-11's list of allowed loads doesn't cover it, this is a deliberate departure, mitigated by a fuse at the source, "always live" labels, and a relay that disconnects completely when the unit is off.
- **6.6, LC filter and a 9 to 36 V regulator.** The LC filter is optional (add it if radios pick up noise); parts must survive 30 V after the TVS.
- **6.6, "Output 5.1 V at 5 A."** Now 5.0 to 5.3 V.
- **6.7, enclosure.** Adds a heat path: a finned aluminum heat sink in a gasketed cutout in the back wall (part 20, owner chose option A, 2026-10-31).
- **7, NMEA 2000 interface.** The suggested Copperhill PiCAN-M is disqualified (not isolated); the interface must be galvanically isolated.

## Open questions before buying

- **Standby power near the helm.** Owner is checking the boat's wiring diagrams for an existing standby (unswitched) circuit at the helm. If there is none, run a new fused feed from the battery side of the main switch (part 19 sets the gauge by length).
- **House battery standby point.** Standby power comes from the house battery (owner, 2026-10-31); find its battery-side connection on the diagram.
- **Sense source.** Which switched circuit at the helm the sense wire taps: one that stays live while cranking, not ignition or accessory (it needs a 1 A fuse).
- **Does cranking reach the house battery?** The boat has a main engine and a kicker. If the house battery is kept apart from starting, a standard 75% coil should hold; if not, the crank test decides, and a more sensitive coil may be needed (part 4d).
- **Relay and controller.** Pick a relay that meets part 4d (coil 0.6 W or less) and a controller board.
- **Display 12 V maximum.** 4D gives "12.0 V typ" with no maximum. Without a stated 30 V maximum, add a display regulator (part 6).
- **Display power-on.** Does the 4D panel come on by itself when powered? Its power button is on a board that isn't included.
- **Display USB power backfeed.** 4D's datasheet says the touch port also takes power, so the USB power blocker (part 15) is on the buy list.
- **Display orientation.** 4D's drawing shows a portrait panel; Digi-Key lists 1280x800. Confirm the HDMI board outputs landscape.
- **CAN HAT standoff height.** Waveshare doesn't state what standoffs ship with the 27338 or whether they clear the Active Cooler. Check on arrival; buy 16 mm M2.5 standoffs and a header extender if needed.
- **CAN HAT isolation voltage.** Not published. Optional question to Waveshare.
- **Enclosure drawing.** Octopart's inside dimensions for the 1554X2GY need confirming on Hammond's drawing.
- **Free tee port.** Look at the backbone. If none, add a Micro-C T-connector.
- **Spare helm switch or fuse circuit.** If the helm panel has one, it can replace the inline fuse holder and the switch on the box.
- **Tariffs.** Digi-Key shows "tariff may apply" on several parts; the amount shows only in the cart.

Prices are US, before tax and shipping, from product pages on the dates given. Recheck before ordering.
