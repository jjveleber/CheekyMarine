# DIY helm display: component buyer specs

What each part of the main-helm Pi unit must do, so any product can be judged against it. These are requirements, not product picks. Each section ends with the part we already found, labeled **reference, not a requirement**, with the price and the date it was read. Nothing has been bought yet (decision to build: 2026-10-30). Written 2026-10-31.

How to read each section:

- **Job**: what the part does and what it connects to.
- **Must have**: the numbers a product has to meet, and where to find each one on a product page or datasheet.
- **Nice to have**: worth paying a little more for.
- **Disqualifiers**: walk away, and why.
- **Fits with**: limits set by the other parts.

If a product page doesn't state a must-have number, treat it as missing. Ask the seller or move on.

## How it all connects

```
 BOAT 12 V (helm fuse panel, or battery bus)
   |
 [1] FUSE 7.5 A, at the source end
   |
   |   16 AWG duplex cable, about 3 ft
   |
 ==|=== gland G1 =================== ENCLOSURE ==========================
   |
   +--[2] TVS across + and -   (clamps spikes, blows the fuse if it fails short)
   |
 [3] SOFT-POWER SWITCH  <--- [4] SEALED BUTTON, contact 1   (press: power on)
   |  (cuts everything      [4] SEALED BUTTON, contact 2 ---> Pi GPIO in   (hold 2 s: shut down)
   |   when off)            Pi GPIO out ---> switch OFF pin (after shutdown)
   |
   +---------------------------------+
   |                                 |
 [5] BUCK 12 V to 5.3 V, 5 A      [6] DISPLAY POWER: 12 V input,
   |                                  or its own regulator
   |  [7] USB-C power lead             |
   v                                   v
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

Mount [17] holds the enclosure [16] on the dash shelf. Glands [18] seal the two cable entries. Wire [19] covers the 12 V feed and everything inside the box.

Order of the power path matters: fuse first (protects the cable), then TVS (always across the feed), then the soft-power switch (so "off" cuts both the Pi and the display), then the buck and the display.

## At a glance

| # | Part | The one number that matters most | Reference price |
|---|---|---|---|
| 1 | Fuse + holder | 7.5 A blade fuse, sealed holder for 16 AWG | $4.58 (5 A bench fuse) |
| 2 | TVS diode | Unidirectional, 15 to 18 V standoff, 1500 W | $1.06 |
| 3 | Soft-power switch | Off draw in microamps, separate ON and OFF inputs | $8.95 |
| 4 | Sealed pushbutton | IP67 front, momentary, two NO contacts | $42.46 |
| 5 | Buck regulator | 5 A continuous at 5.1 to 5.3 V, survives 30 V+ in | $47.95 |
| 6 | Display power | Display safe from 9 to 16 V, or its own regulator | $0 if built in |
| 7 | USB-C power lead | 20 AWG or heavier, 1 ft or shorter | $7.99 (2-pack) |
| 8 | Raspberry Pi 5 | 8 GB | $175.00 |
| 9 | Cooler | Fits under the CAN HAT (13.7 mm tall reference) | $5.00 |
| 10 | NVMe adapter + SSD | Mounts under the Pi; SSD on a Pi 5 tested list | $29.99 + $49.66 |
| 10b | microSD | A2, 16 to 64 GB | $31.99 |
| 11 | N2K interface | Galvanically isolated, SocketCAN on Pi 5 | $34.99 |
| 12 | N2K drop cable | Micro-C male, 1 m, shielded | $23.95 |
| 13 | Display | 1000 cd/m2 or more, USB HID touch, 9 to 10.1 in | $147.95 |
| 14 | Video cable | micro-HDMI to the display's HDMI type, 1 ft | $12.99 |
| 15 | Touch cable | USB-A to the display's touch port, data wires | often in the display box |
| 16 | Enclosure | IP65 or better, UV stable, 75 mm or more inside depth | $63.22 |
| 17 | Mount | Holds about 2 kg on a dash shelf, no suction | $64.49 |
| 18 | Glands | IP68, clamp range fits each cable | $1.92 (2) |
| 19 | Wire | Tinned marine wire, 16 AWG feed | $21.93 |

## Power budget

The numbers every power part below is sized from.

| Load | Voltage | Worst case | Source |
|---|---|---|---|
| Pi 5 with SSD, CAN HAT, touch | 5 V | 5 A (25 W) | Raspberry Pi's 5 V 5 A supply rating |
| Same, seen at 12 V through an 88% buck | 12 V | about 2.4 A | 25.5 W / 0.88 / 12 V |
| Display, reference panel at 1000 nit | 12 V | 0.65 A | 4D datasheet, 10.1" 1280x800 table |
| **Whole unit** | 12 V | **about 3.1 A** | |
| **Whole unit, battery sagging to 10.5 V** | 10.5 V | **about 3.5 A** | |

Typical draw while charting is well below this; the worst case is what the fuse, switch, buck and wire must carry.

Voltage drop on the feed: 16 AWG copper is about 4 milliohms per foot. A 3 ft run is 6 ft out and back, so 0.024 ohm at 3.5 A drops about 0.09 V (under 1%). Wire gauge is set by toughness and the fuse, not by drop.

Boat voltage the parts must live with: about 12.2 V resting, 14.4 to 14.8 V while charging, dips toward 10 V during engine cranking, and short spikes well above that. The TVS clamps spikes to about 28 V, so everything after it must survive 30 V.

## Power

### 1. Fuse and fuse holder

**Job.** Protects the 12 V feed cable if anything downstream shorts. It belongs at the power source end of the cable, not at the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Fuse type | Blade (ATO/ATC) so spares from the boat's kit fit | Product title or datasheet "ATO", "ATC", "blade" |
| Fuse rating | 7.5 A, 32 V DC | Printed on the fuse; datasheet "voltage rating" |
| Holder current rating | 15 A or more | Holder datasheet "rated current" |
| Holder wire size | 16 AWG leads, or terminals that accept 16 AWG | Datasheet "wire gauge" or lead spec |
| Sealing | Cover that closes over the fuse; "water resistant" or IP rating | Product page; a cap or lid in the photo |
| Location | Within 7 in of the source connection (ABYC E-11) | Install rule, not a product spec |

**Nice to have**

- A spare circuit on the helm's existing fuse panel or switch panel. If there is one, it replaces the inline holder entirely.
- IP67 holder if it will hang in the open cavity below the dash.
- Tinned leads.

**Disqualifiers**

- Glass tube (AGC) holders: tube fuses crack in vibration and the boat kit won't have spares.
- Holders with leads thinner than 16 AWG: the holder lead becomes the weak point the fuse is meant to protect.
- Automotive "add-a-circuit" taps: they ride on another circuit's fuse, so a fault here kills that circuit too.

**Fits with**

- 7.5 A is 2x the 3.5 A worst case, under the 16 AWG wire's rating, and blows on a real short. The 5 A fuse in the bench cart is fine on the bench (no display) and too close to the limit on the boat.
- The holder's leads join the 16 AWG feed (part 19) with crimp butt connectors.

**Reference, not a requirement.** MPD BF353 water-resistant inline ATO holder, 15 A, 16 AWG leads, $4.14, Digi-Key, 2026-10-29. Littelfuse 0287005.PXCN 5 A ATO, $0.44, Digi-Key, 2026-10-29 (bench value; the boat wants 7.5 A).

### 2. TVS diode and filtering

**Job.** Sits across + and - right where the feed enters the box. It does nothing at normal voltage, and clamps short spikes from the alternator, pumps and the starter before they reach the switch, buck and display. If a big spike kills it, it fails short and blows the fuse instead of letting the spike through.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Polarity | Unidirectional | Part number ends in "A" without "CA"; datasheet "uni-directional" |
| Standoff voltage (VRWM) | 15 to 18 V: above 14.8 V charging, as low as possible above it | Datasheet "VRWM" or "reverse stand-off voltage" |
| Clamping voltage (VC) | 30 V or less at rated pulse current | Datasheet "VC" at "IPP" |
| Peak pulse power | 1500 W or more (10/1000 µs) | Datasheet "PPPM" |
| Leakage at standoff | 5 µA or less | Datasheet "IR at VRWM" (it counts in the off-state draw) |
| Package | Through-hole axial or a part that mounts on a terminal strip | Datasheet package drawing |

**Nice to have**

- An automotive load-dump rated TVS (SM8S class, 6600 W, AEC-Q101) instead of a 1500 W part. A 1500 W TVS handles switching spikes, not a full alternator load dump.
- A snap-on ferrite on the 12 V feed inside the box, plus a small LC filter (inductor plus capacitor), only if the VHF or AM radio picks up noise once installed. Don't buy until there is a symptom.

**Disqualifiers**

- Standoff below 15 V: the TVS starts conducting while the engine is charging and cooks.
- Clamping above 32 V: the soft-power switch (part 3) is rated 32 V recommended, 40 V absolute.
- MOVs (varistors) in place of a TVS: they wear out with each spike and clamp loosely.

**Fits with**

- Must be after the fuse (part 1), so a shorted TVS blows the fuse.
- Its clamp voltage sets what everything downstream must survive: switch 40 V max, buck 60 V max, display must take 30 V or sit behind its own regulator (part 6).

**Reference, not a requirement.** Littelfuse 1.5KE20A: 17.1 V standoff, 27.7 V clamp, 1500 W, unidirectional, $1.06, Digi-Key, 2026-10-30.

### 3. Soft-power switch

**Job.** The unit's on/off. Press the button and it turns the whole unit on. When the owner holds the button for 2 s, the Pi shuts down cleanly and then pulses the switch's OFF input, which cuts power to the Pi and the display. When off it draws next to nothing, so the unit can stay wired to the battery.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Input voltage | 9 to 16 V operating; 30 V or more absolute maximum | Product page "operating voltage" and "absolute maximum" |
| Continuous current | 5 A or more at 50 °C or warmer | Current spec at a stated temperature, not only the peak |
| Off-state current | Microamps (under 10 µA) | Product page "off current" or "standby current" |
| ON input | Turns on from a momentary contact to ground or a pulse | Pin description |
| Separate OFF input | Turns off from a logic-level pulse (3.3 V high is enough) | Pin description, threshold voltage |
| Button press when on | Must NOT turn the unit off by itself (the Pi decides) | Pin description: an "on-only" button connection |
| Reverse-voltage protection | Yes | Product name or features |

**Nice to have**

- Indicator LED output for an illuminated button.
- Screw terminals or 0.1 in header holes for clean wiring.

**Disqualifiers**

- Latching or toggle switches in the power line: pulling power without a clean shutdown risks the filesystem (spec 6.6 wants a clean shutdown on every normal power-off).
- Modules where every button press toggles power and there's no on-only connection: one bump of the button would cut the Pi mid-write.
- Relay-based modules: the relay coil draws milliamps while on and clicks; some also draw current when off.
- Modules rated only to 5 V or 12 V nominal with no stated maximum.

**Fits with**

- Sits after the TVS and before the buck (part 5) and the display power (part 6), so off means everything is off (spec 6.6).
- The button (part 4) needs two contacts, one for this switch's ON input and one for a Pi GPIO, or one contact plus a blocking diode. The exact circuit is plan 5's job.
- The OFF input is driven by a Pi GPIO; a 3.3 V logic high must exceed its threshold.

**Reference, not a requirement.** Pololu Big Pushbutton Power Switch with Reverse Voltage Protection, HP, #2813, $8.95, Pololu, 2026-10-30. Per its product page (read 2026-10-31): 4.5 to 32 V recommended, 40 V absolute maximum, 6 A at 55 °C, under 0.2 µA off, ON and OFF inputs trigger above 1 V, and a button from pin A to ground gives on-only operation. Its onboard button still toggles, but it sits inside the closed box.

### 4. Sealed pushbutton

**Job.** The one control on the outside of the box. Press to turn on; hold 2 s to shut down.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Action | Momentary | Product title "momentary" |
| Front sealing | IP67 (IP65 minimum) when panel-mounted | Datasheet "front IP rating" |
| Contacts | 2 normally open (2NO), or 1NO (then a diode is added) | Datasheet "contact configuration" |
| Contact rating | Low-level switching works: gold-plated contacts, or rated down to 1 mA at 5 V | Datasheet "contact material", "minimum load" |
| Panel hole | 16, 19 or 22 mm | Datasheet "mounting hole" |
| Behind-panel depth | 40 mm or less | Datasheet drawing |
| Body | Stainless steel or anodized aluminum, or UV-stable plastic | Datasheet "material" |

**Nice to have**

- LED ring that shows the unit is on (12 V LED fed from the switched rail, or 5 V).
- Flush or slightly raised actuator, so a knee or line can't press it.
- Screw or solder terminals instead of flying leads.

**Disqualifiers**

- Latching (push-on, push-off) buttons: the button must spring back so the Pi can time the hold.
- Silver-only contacts rated for mains loads: at a few microamps they can fail to make reliable contact.
- No IP rating, or an IP rating only for the switch body behind the panel.

**Fits with**

- Contact 1 goes to the soft-power switch's ON input (part 3), contact 2 to a Pi GPIO.
- Its hole goes in the enclosure (part 16) away from where a hand rests on the display.

**Reference, not a requirement.** EAO 82-5751.1000, 19 mm momentary, IP65/IP67, $42.46, Digi-Key, 2026-10-30. Check its contact block configuration before buying; a 2NO block may be a separate part number.

### 5. Buck regulator (12 V to 5.3 V)

**Job.** Turns boat 12 V into the 5 V the Pi needs, at up to 5 A, through every voltage the boat throws at it.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Input range | 9 to 16 V operating; survives 30 V or more | Datasheet "input voltage range" and "absolute maximum" |
| Output voltage | 5.1 to 5.3 V fixed, or adjustable to it | Datasheet "output voltage", accuracy 3% or better |
| Output current | 5 A continuous at 12 V input, at 50 °C ambient | "Maximum continuous output current" graph or table versus input voltage; ignore peak numbers |
| Topology | Switching (buck) | Datasheet; efficiency spec present |
| Efficiency | 85% or better at 2 to 4 A | Efficiency graph |
| Protection | Reverse polarity, overcurrent, over-temperature | Feature list |
| Mounting | Holes or a mounting tab | Photo, drawing |

**Nice to have**

- A USB-C PD source that advertises 5 V 5 A. The Pi then runs its USB ports at full current without the `usb_max_current_enable=1` config line. Rare; don't pay much for it.
- A power-good output (handy for bring-up checks).
- Made by a maker that publishes graphs, not just a headline number.

**Disqualifiers**

- Linear regulators (LM7805 class): at 12 V in and 5 A out they'd turn 35 W into heat inside a sealed box.
- Unbranded "12 V to 5 V 5 A car converter" modules with no datasheet or efficiency graph: many sag or overheat well below their label.
- USB car chargers (cigarette-lighter plugs): no clean wired input, and most can't supply 5 A at 5 V.
- 5.0 V fixed output with no adjustment: after the lead's voltage drop the Pi sees under 5 V and throttles.
- Maximum input below 30 V: it wouldn't survive what the TVS lets through.

**Fits with**

- Output must not feed the display if the display's 5 V input stops at 5.2 V (the 4D reference does); 5.3 V is above that.
- Output goes into the USB-C power lead (part 7) to the Pi's USB-C port, never to 12 V or the GPIO 5 V pins.
- 5.3 V minus about 0.1 V drop in a 1 ft 20 AWG lead at 5 A gives the Pi about 5.2 V. Confirm on the bench with `vcgencmd get_throttled` (must read `throttled=0x0`).

**Reference, not a requirement.** Pololu D42V55F5.3, $47.95, Pololu, 2026-10-29 (in the bench cart). Per its product page (read 2026-10-31): 5.3 V within 3%, input up to 60 V, reverse-voltage protection, typically 6 A at 42 V in (4 to 8 A depending on voltages, no heatsink, room temperature), 25.4 x 25.4 x 9 mm. Its current graph at 12 V in should be checked against the 5 A need; it has no published temperature derating.

### 6. Display power

**Job.** Feeds the display from the switched 12 V, safely across 9 to 16 V and the 30 V the TVS lets through. This is a requirement on the display (part 13) first; a separate regulator is only bought if the chosen display can't meet it.

**Must have, one of:**

- **A. 12 V input on the display** with a stated range covering 9 to 16 V continuous (a datasheet "maximum input" of 16 V or more), and either a 30 V rating or a regulator in front of it.
- **B. Its own regulator.** If the display's input is 5 V only, or 12 V with no stated maximum: a regulator for the display alone, from the switched 12 V.
  - 5 V displays: a second buck with 5.0 V output (not 5.3 V), rated 1.5x the display's current.
  - 12 V displays with an unknown maximum: a buck-boost (step-up/step-down) regulator with 12 V output, input 9 to 30 V or wider, rated 1.5x the display's current (about 1 A for the reference panel).

**Disqualifiers**

- Powering the display from the Pi's USB ports. The Pi 5 shares 1.6 A across all four ports, and a 1000-nit panel draws more than that at 5 V (1.7 A for the reference).
- Powering a 5 V display from the Pi's 5.3 V buck when the display's maximum is under 5.3 V.
- A 12 V display wired straight to the feed when its datasheet gives no maximum.

**Fits with**

- Fed after the soft-power switch (part 3) so the display is off when the unit is off.
- The reference display has a 12 V barrel jack with "12.0 V typ" and no published maximum, so it falls under B until 4D Systems confirms a range.

**Reference, not a requirement.** None priced yet. Buy only if 4D Systems (or the chosen display's maker) can't confirm a 16 V maximum.

### 7. USB-C power lead (buck to Pi)

**Job.** Carries the buck's 5.3 V into the Pi's USB-C power port. Using the port, not the GPIO 5 V pins, keeps the Pi's own input protection in the path.

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

- Thin (24 to 28 AWG) charging pigtails: half a volt of drop at 5 A, and the Pi throttles.
- Leads longer than needed: every foot adds drop.

**Reference, not a requirement.** ELNONE USB-C pigtail, 20 AWG, 6-wire, 1 ft, 2-pack, $7.99, Amazon, 2026-10-29 (in the bench cart).

## Compute and storage

### 8. Raspberry Pi 5, 8 GB

**Job.** Runs the chart app, the map rendering on its GPU, and the NMEA 2000 daemon. Everything else plugs into it.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Model | Raspberry Pi 5 | Title and photo: two micro-HDMI, PCIe connector, power button |
| Memory | 8 GB (owner's choice, headroom for future chart layers) | Title, part number SC1112 (or SC1432, see below) |
| Seller | Raspberry Pi approved reseller, or the reseller's own Amazon store | raspberrypi.com product page "Buy" list |
| Operating range | 0 to 50 °C ambient (the board's own rating) | Raspberry Pi 5 product brief |

**Nice to have**

- Buying from the same seller as the cooler (part 9) to save shipping.

**Disqualifiers**

- Kits with a wall power supply, case, or SD card: paying for parts this build replaces.
- Compute Module 5, Pi 500, Pi 4: different board, different fit. The software targets the Pi 5.
- 2 GB or 4 GB: below the owner's chosen headroom.
- Marketplace sellers with no reseller status: counterfeit and relabeled boards exist.

**Fits with**

- Board 85 x 56 mm. Its USB-C, micro-HDMI and PCIe connectors are on the edges, so the enclosure (part 16) needs room beside it for plugs and cable bends, not just above it.
- The 40-pin header carries the CAN HAT (part 11); the PCIe connector carries the NVMe adapter (part 10).
- 0 to 50 °C is the limit to watch inside a sealed box in sun. That is why the cooler matters.

**Reference, not a requirement.** Raspberry Pi 5, 8 GB, SC1112, $175.00, Digi-Key, 2026-10-29 (rechecked 2026-10-30: $175.00, in stock). Digi-Key's page showed part SC1432; confirm it reads "Raspberry Pi 5, 8 GB". Same price at CanaKit.

### 9. Cooler

**Job.** Keeps the Pi below its throttling temperature inside a closed, warm box. A fan inside a sealed box only stirs the air, so this works together with the box's surface area and color (part 16).

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
| Seller | Sold by the brand, or by the retailer itself | "Sold by" line |

**microSD: must have**

| Spec | Requirement | How to check |
|---|---|---|
| Class | A2 (A1 acceptable), U3 | Logo on the card photo, title |
| Capacity | 16 to 64 GB | Title |
| Seller | Sold by the brand or the retailer itself | "Sold by" line |

**Nice to have**

- SSD with TLC flash and a published endurance (TBW) figure.
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
- On arrival, `lspci -nn` names the controller; soak-test booting inside the return window (see the bring-up checklist).
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
- Uses SPI and two interrupt GPIOs; the soft-power button and OFF signal need two more free GPIOs.
- Wires to the drop cable (part 12): CAN_H to NET-H (white), CAN_L to NET-L (blue), isolated GND to NET-C (black). NET-S (red) and the shield stay unconnected. Termination off.

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
| Power | Meets part 6: 9 to 16 V safe, or 5 V from its own regulator | Datasheet "input voltage" with a min and max |
| Power draw | Stated at full brightness | Datasheet current table |
| Operating temperature | -10 to +60 °C or wider | Datasheet |
| Storage temperature | -20 to +70 °C or wider | Datasheet |
| Dimming | Can dim far enough for night use | OSD menu or DDC/CI brightness control |
| Mounting | Tabs, bezel or holes to fix it behind a cutout | Mechanical drawing |
| Depth | Stated; 25 mm or less | Mechanical drawing |

**Nice to have**

- Touch glass optically bonded to the LCD (less glare, no condensation gap).
- Cover-lens-bezel version: the glass is bigger than the LCD, which makes sealing it into a cutout much easier than sealing a 1:1 glass edge.
- DDC/CI brightness control over HDMI, so the app can dim the screen at night.
- Anti-glare or anti-reflective glass treatment.
- Touch that ignores water drops (test before cutting the enclosure, spec section 8).
- Readable through polarized sunglasses in landscape (test).

**Disqualifiers**

- Brightness under 1000 nits, or no number given.
- DSI, SPI or GPIO-header displays: the header is taken by the CAN HAT, and these panels are dim.
- Resistive touch, or touch that needs a vendor driver or Windows software.
- Power only over the touch USB cable from the Pi: the Pi can't supply it.
- No mechanical drawing: the enclosure cutout can't be planned.
- Finished monitors at $700 or more (Beetronics, Xenarc): they push the DIY total near $1,100 (cost comparison).

**Fits with**

- Input voltage against part 6 and the buck's 5.3 V (part 5).
- Its HDMI connector type sets the video cable (part 14); its touch port type sets the touch cable (part 15).
- Outline plus a sealing border sets the enclosure lid size; depth plus the Pi stack sets the enclosure depth (part 16).
- If the touch USB-C port also accepts power, check it doesn't draw from the Pi's USB when powered from 12 V (ask the maker).

**Reference, not a requirement.** 4D Systems 4DHDMI-101-1280-800-CT-EAR-1000, $147.95, Digi-Key, 2026-10-30 (4 in stock). Per 4D's datasheet R1.3: IPS, 1280x800, 1000 cd/m2, capacitive touch glass optically bonded, metal mounting tabs, mini-HDMI (HDMI 1.4), DDC supported, USB-C for touch and 5 V power (4.8 to 5.2 V, 1700 mA) or 12 V barrel jack (650 mA, "12.0 V typ", no maximum given), -20 to +70 °C operating, -30 to +80 °C storage. RS lists 15.98 mm depth. Open: 12 V maximum, native orientation, and USB power backfeed (see open questions). Variant to price: 4DHDMI-101-1280-800-CT-CLB-1000 (cover lens bezel).

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
| Length | 50 cm or shorter | Title |

**Nice to have**

- Right-angle ends.

**Disqualifiers**

- Charge-only cables: touch never shows up.

**Fits with**

- Use a USB 2 port (black) on the Pi.
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
| Inside length and width | Display outline plus about 20 mm per side for the sealing border | Inside dimensions on the drawing (not outside) |
| Inside depth | 75 mm or more for a 16 mm display (display plus about 45 mm Pi stack plus cable room) | Drawing; base depth plus lid depth |
| Lid | Flat enough to cut a display window and mount the panel | Drawing; a flat lid, not domed |
| Hardware | Stainless or captive lid screws | Datasheet |
| Temperature | -20 to +80 °C or wider | Datasheet |

**Nice to have**

- Light color (grey or white): absorbs less sun.
- A pressure-equalizing vent (IP67 membrane breather): keeps temperature swings from pumping moist air past the seals.
- Internal mounting bosses or an inner panel to fix the Pi stack to.
- A clear-lid version is not needed; the display window is cut.

**Disqualifiers**

- No IP rating, or IP54 and below.
- Plain ABS without UV stabilization: goes brittle in sun.
- Metal boxes: block Wi-Fi, which the update page needs.
- Inside depth under 75 mm with a 16 mm panel.
- Dark colors in direct sun, unless nothing else fits.

**Fits with**

- Heat: the electronics put out about 5 to 15 W. A box of the reference size (about 0.2 m2 of surface) runs very roughly 10 °C above the cabin, before sun. The Pi's limit is 50 °C ambient.
- Display outline (part 13), stack height (parts 8, 9, 10, 11), cable side room (part 14), button hole (part 4), two gland holes (part 18), mount plate (part 17).
- Measure the real Pi stack on the bench before choosing the depth.

**Reference, not a requirement.** Hammond 1554X2GY, polycarbonate, 300 x 200 x 90 mm outside, IP66/67/68, NEMA 4X, grey, $63.22, Digi-Key, 2026-10-30. 90 mm outside is tight for the stack; the deeper 1554XA2GY is not priced yet, and neither inside depth is confirmed.

### 17. Mount

**Job.** Holds the enclosure on the flat dash shelf left of the wheel, beside the Garmin, tilted toward the helm seat.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| Load | About 2 kg (enclosure, display, electronics) with boat vibration | Maker's load rating for the ball size |
| Base | Screws or bolts to a flat shelf | Base plate drawing, hole pattern |
| Adjustment | Tilt and swivel, lockable | Product page |
| Materials | Marine: anodized aluminum, glass-filled composite, stainless hardware | Product page |
| Enclosure side | Plate that bolts through the box with sealed fasteners | Plate drawing and hole pattern |

**Nice to have**

- Short or medium arm: shorter shakes less.
- A second, identical ball base so the unit can move (rear helm, bench).

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
- A sealed 2-pin connector (Deutsch DT class) on the 12 V side for the same reason.

**Disqualifiers**

- Grey nylon without UV stabilization.
- Running two loose single wires through one round gland: it can't seal them. Use a round jacketed 2-conductor cable (part 19) or a multi-hole insert.

**Reference, not a requirement.** Altech 5308 509, PG9 nylon, IP68, 2 for $1.92, Digi-Key, 2026-10-30. Check its clamping range against both cables.

### 19. Wire and terminals

**Job.** The 12 V feed from the source to the box, and the short runs inside the box.

**Must have**

| Spec | Requirement | How to check |
|---|---|---|
| 12 V feed | 16 AWG, tinned copper, fine-stranded marine wire (UL 1426 boat cable or SAE J1127/J1128) | Product page "tinned", "UL 1426", "marine" |
| Feed form | Round jacketed duplex (red and black or red and yellow) for the gland | Product page "duplex", "2-conductor" |
| Length | About 3 ft for the run (under 2 ft) plus a service loop | |
| Inside the box | 22 AWG tinned for the button and GPIO signals | Product page |
| Terminations | Crimp terminals and adhesive-lined heat shrink | Product page "heat shrink", "marine" |

**Nice to have**

- Pre-made heat-shrink butt connectors.
- Labels on both ends of the feed.

**Disqualifiers**

- Bare (untinned) copper: corrodes inside the jacket.
- Solid-core or automotive single-strand wire: cracks in vibration.
- Solder-only joints with no strain relief: crack in vibration.

**Fits with**

- 16 AWG is protected by the 7.5 A fuse (part 1) with lots of margin; drop is about 0.09 V at worst-case load.
- Cable outside diameter sets the gland (part 18).

**Reference, not a requirement.** Ancor 16 AWG tinned primary wire, 25 ft red (182803) and 25 ft black (182003), $21.93 total, Amazon, 2026-10-30. That is single conductor; for a gland, duplex jacketed cable seals better.

## Fit checks across parts

Before ordering the boat parts, these have to agree with each other:

1. **Voltage chain.** Boat 9 to 16 V, spikes clamped to about 28 V by the TVS. Switch 40 V max, buck 60 V max, display must take 30 V or have its own regulator. The buck's 5.3 V goes only to the Pi.
2. **Stack height.** NVMe adapter under the Pi, Pi, Active Cooler (13.7 mm), CAN HAT on standoffs of about 16 mm. About 45 mm total (estimate; measure on the bench).
3. **Enclosure depth.** Display depth (16 mm reference) plus stack plus cable room fits the inside depth. 75 mm or more inside.
4. **Enclosure footprint.** Display outline plus about 20 mm of border, plus room beside the Pi for the micro-HDMI and USB-C plugs.
5. **Connector types.** Display's HDMI type matches the video cable; display's touch port matches the touch cable; drop cable is male at the tee.
6. **GPIO budget.** CAN HAT uses SPI and two interrupt pins; the button sense and the OFF signal need two more free GPIOs.
7. **Current.** Fuse 7.5 A, switch 6 A at 55 °C, buck 5 A, wire 16 AWG, against a 3.5 A worst case at 12 V.

## Open questions before buying

- **Display 12 V maximum.** 4D gives "12.0 V typ" for the barrel jack with no maximum. Ask 4D. If they can't say 16 V or more, add a display regulator (part 6).
- **Display USB power backfeed.** With the display on 12 V, does its USB-C touch port also draw from the Pi? Ask 4D.
- **Display orientation.** 4D's drawing shows a portrait panel; Digi-Key lists 1280x800. Confirm the HDMI board outputs landscape.
- **CAN HAT standoff height.** Waveshare doesn't state what standoffs ship with the 27338 or whether they clear the Active Cooler. Check on arrival; buy 16 mm M2.5 standoffs and a header extender if needed.
- **CAN HAT isolation voltage.** Not published. Optional question to Waveshare.
- **Enclosure inside depth.** Not confirmed for the 1554X2GY or the deeper 1554XA2GY. Read Hammond's drawing.
- **Button contacts.** Confirm the EAO 82-5751.1000 has two NO contacts, or plan for the diode.
- **Free tee port.** Look at the backbone. If none, add a Micro-C T-connector.
- **Spare fuse panel circuit.** If the helm panel has one, skip the inline holder.
- **Tariffs.** Digi-Key shows "tariff may apply" on several parts; the amount shows only in the cart.

Prices are US, before tax and shipping, from product pages on the dates given. Recheck before ordering.
