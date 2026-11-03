# Laptop proof of concept: hookup

How the touchscreen laptop proof of concept connects to boat power and the NMEA 2000 backbone. Written 2026-11-02, before the parts arrived; checks marked "on arrival" have not been done yet.

The Pi build in the other docs here is parked, not dropped. This laptop setup is the proof of concept that decides whether the Pi build comes back. Success is one trip with charts plus live depth, GPS and AIS on the laptop at the helm.

The laptop design doc (OS setup, auto-login, plotter auto-start, mounting in the cedar sleeve) comes next and is separate from this hookup doc.

## Parts

| Part | Pick | Status |
|---|---|---|
| Tablet | Dell Latitude 7320 Detachable, i7-1180G7, 16 GB, 256 GB, keyboard, 65 W Dell USB-C charger (eBay 307244203304, Swing Computers, $383.99) | bought 2026-11-02 |
| 12 V charger | Estbuc flush-fit 125 W car charger (65 W PD USB-C plus 60 W QC USB-A), [B0GX1YDB8P](https://www.amazon.com/dp/B0GX1YDB8P) | already on the boat |
| Charge cable | UGREEN 100 W 5 A USB-C to USB-C, 3.3 ft braided, 2-pack, [B09N94MZG9](https://www.amazon.com/dp/B09N94MZG9) | ordered 2026-11-02 |
| CAN adapter | DSD TECH SH-C30G isolated USB to CAN (CANable 1.0 Pro, candleLight gs_usb firmware), [B0CDGGBZDT](https://www.amazon.com/dp/B0CDGGBZDT) | ordered 2026-11-02 |
| Adapter cable | UGREEN USB-C to USB-B, 3 ft braided, [B086ZGYK6K](https://www.amazon.com/dp/B086ZGYK6K) | ordered 2026-11-02 |
| NMEA 2000 drop | Regatta Processing 2 m Micro-C drop cable (cut one end), [B08SCJVRGZ](https://www.amazon.com/dp/B08SCJVRGZ) | ordered 2026-11-02 |
| Ferrules | SOMELINE ferrule kit, AWG 24 to 8, 23 sizes, [B09FSWKRH5](https://www.amazon.com/dp/B09FSWKRH5) | ordered 2026-11-02 |

Fallback charger, only if the Estbuc falls short (see [Power](#power)): Anker 167.5 W 3-port car charger, [B0CZ7BL16W](https://www.amazon.com/dp/B0CZ7BL16W), $37.79. Not ordered.

Nothing else is needed. The 7320 has two Thunderbolt 4 (USB-C) ports and nothing else, so one port charges and the other takes the CAN adapter.

## Overview

```
 helm 12 V lighter socket (10 A)
   |
 Estbuc flush charger, USB-C 65 W PD port
   |
 UGREEN 100 W USB-C cable
   |
 Dell 7320  TB4 port 1 (power in)
            TB4 port 2 (data)
               |
             UGREEN USB-C to USB-B cable, 3 ft
               |
             SH-C30G adapter  (termination OFF, isolated)
               |  4-pin screw terminal
             cut Regatta 2 m drop
               |  Micro-C male
             backbone tee, just under the dash
```

The laptop runs on its own battery, charged from the 12 V socket. It takes no power from the NMEA 2000 bus, and the adapter's isolation keeps the laptop's ground separate from the bus.

## Power

Chain: helm 12 V lighter socket (rated 10 A, owner, 2026-11-02) to the Estbuc USB-C 65 W port, through the UGREEN 100 W cable, into either Thunderbolt port on the Dell. Use port 1 for power by habit so port 2 is always the CAN adapter.

Load at 12 V:

| Load | Current |
|---|---|
| Dell charging at 65 W (charger losses included) | about 6 A |
| Dell plus one phone on the USB-A port | about 8 A, fits the 10 A socket |
| All charger ports at full load (125 W) | about 12 A, does not fit |

Keep it to the Dell plus one phone.

The Estbuc listing says the full 65 W comes only "in a 20V car", which is unclear. The plan is to try it first. Buy the Anker fallback only if the Dell shows a "slow charger" warning or its battery drains while the plotter runs. If the Anker is bought, check whether its included cable is rated 100 W; if the Dell still warns, use the UGREEN 100 W cable instead.

Set the Dell's BIOS battery charge mode to "Primarily AC use" or a custom 50 to 80% range. The tablet sits on the charger for hours at a time in a warm cabin, and a full charge held hot wears the battery fastest.

## NMEA 2000 connection

### Adapter settings

- **Termination: OFF.** The backbone already has its two 120 ohm terminators, one at each end. The adapter is on a drop, and a third terminator would load the bus. Check the switch before connecting; confirm it on arrival with a meter across CAN_H and CAN_L on the adapter's terminal with nothing connected (OFF reads open, ON reads about 120 ohm).
- **Firmware:** candleLight (gs_usb), which the Linux kernel drives with no install. DSD TECH says units shipped from September 2026 have their newer build (uses the 24 MHz crystal, lights the TX/RX LEDs); older units work with the stock build and can be updated over USB if wanted.
- **Interface:** appears as `can0`. NMEA 2000 runs at 250 kbit/s.
- **Listen-only:** n2kd never transmits by default. Bring the interface up in listen-only mode too, so the adapter cannot send even an error frame or ACK onto the boat's bus.

### SH-C30G terminal

The listing gives the 4-pin 5.0 mm terminal as CAN_L, CAN_H, isolated GND, isolated +5 V, and says pin 3 is isolated GND. Check the silkscreen on arrival before wiring; trust the board over this table.

| Terminal | Signal | Connect |
|---|---|---|
| 1 | CAN_L | blue (NET-L) |
| 2 | CAN_H | white (NET-H) |
| 3 | isolated GND | black (NET-C) |
| 4 | isolated +5 V out | nothing, leave empty |

### Drop cable wires

Micro-C wiring is standard across NMEA 2000 cables:

| Micro-C pin | Name | Color | Regatta gauge | At the adapter |
|---|---|---|---|---|
| 1 | Shield | bare drain | | insulate, leave unconnected |
| 2 | NET-S (bus +12 V) | red | 22 AWG | insulate, tape back, unconnected |
| 3 | NET-C (bus 0 V) | black | 22 AWG | terminal 3 |
| 4 | NET-H | white | 24 AWG | terminal 2 |
| 5 | NET-L | blue | 24 AWG | terminal 1 |

Why each one:

- **NET-C to isolated GND:** gives the isolated CAN transceiver the bus's own 0 V as its reference. Without it the transceiver floats and may read the bus badly.
- **NET-S unconnected:** the adapter powers itself from USB through its isolated converter. NET-S is live 12 V whenever the bus is powered; a loose red wire touching anything blows the bus fuse and drops every instrument, so cap it properly.
- **Shield unconnected at this end:** NMEA 2000 ties the shield to ground at one point only, near the bus power feed. Grounding it here too makes a loop.
- **+5 V out unused:** it exists to power a small node; nothing here needs it.

### Making the cable

1. Keep the **male** Micro-C end; it plugs into the drop port on the backbone tee just under the dash. Cut off the female end. The tee is close, so most of the 2 m is spare; leave enough to reach where the adapter mounts behind or under the cedar sleeve, plus a drip loop.
2. Before stripping, confirm the colors with a meter: continuity from each pin of the male plug to its wire. Use the plug's pin numbers molded on the face, or the standard Micro-C male pinout. If any color differs from the table, follow the meter.
3. Strip the outer jacket back about 40 mm. Cut the bare drain short and cover it with heat shrink. Cut the red wire short, cover its end with heat shrink, fold it back and tape it to the jacket.
4. Strip white, blue and black about 8 mm (or the length the ferrule's metal sleeve needs).
5. Crimp ferrules: **0.25 mm2** on the 24 AWG white and blue, **0.34 mm2** (or 0.5 mm2 if that is what the kit has) on the 22 AWG black.
6. Land them on the terminal per the table: blue 1, white 2, black 3, terminal 4 empty. Tug each wire after tightening.
7. Zip-tie the cable jacket to the adapter or its mount so a pull on the cable loads the jacket, not the screw terminal.

### Mounting

Mount the adapter behind or under the cedar sleeve where it stays dry and the USB-B plug is not bent. Route the USB cable and the drop with a drip loop below the adapter so water runs off before reaching it.

## Bench checks on arrival

Inside the 30-day return windows, at home, before the boat is back:

1. **Battery:** run `powercfg /batteryreport` in Windows before wiping (design capacity against full charge capacity; the seller stated 39,604 of 39,604 mWh).
2. **Touch and rotation on Ubuntu:** boot a live USB, check touch, and check the screen turns when the keyboard is detached and the tablet rotates.
3. **Adapter enumerates:** plug the SH-C30G into port 2, then:

   ```
   ip -details link show can0
   ```

   It should show a `can` link driven by gs_usb.
4. **Termination switch:** meter check per [Adapter settings](#adapter-settings), with the terminal empty.
5. **Sunlight:** the 7320 is rated 500 nits, never measured. Look at the plotter at full brightness in direct sun before the trip.
6. **BIOS charge mode** set as in [Power](#power).

## Dock test

When the boat is back (see the boat checks: the backbone needs a free Micro-C tee drop port first):

1. Instruments on, so the bus is powered and talking.
2. Plug the drop into the tee, adapter into Dell port 2.
3. Bring the interface up, listen-only:

   ```
   sudo ip link set can0 up type can bitrate 250000 listen-only on
   ```

4. Watch traffic:

   ```
   candump can0
   ```

   Frames should scroll steadily. Look for depth (PGN 128267), position (PGN 129025 or 129029) and, with the AIS on, AIS reports (PGN 129038 and 129039).
5. Check for errors:

   ```
   ip -details -statistics link show can0
   ```

   The state should be `ERROR-ACTIVE` and the error counters near zero. Errors usually mean CAN_H and CAN_L are swapped or termination is on.
6. Start n2kd with `--can can0` and the plotter, and check depth, position and AIS on the chart.

If it all works, the next step is the trip test.
