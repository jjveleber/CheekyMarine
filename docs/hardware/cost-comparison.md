# Hardware cost: DIY unit vs a second Garmin

Prices were read from product pages on 2026-10-29 (bench carts) and 2026-10-30 (everything else). They are US prices before tax and shipping unless marked. Nothing has been bought yet. Prices move often, so recheck before ordering.

## Summary

| Option | Where it mounts | Total before tax | Shows Garmin sonar/radar |
|---|---|---|---|
| **DIY Pi unit** (10.1", 1000 nit) | Main helm, beside the 943xsv | **$790.05** ($833.24 with tax and shipping on the bench carts) | No |
| Garmin GPSMAP 743 (7"), networked | Rear helm | **$1,564.96** | Yes |
| Garmin GPSMAP 943 (9"), networked | Rear helm | **$1,864.96** | Yes |
| Garmin GPSMAP 1243 (12"), networked | Rear helm | $3,164.96 | Yes |
| Garmin ECHOMAP UHD2 74sv / 94sv, not networked | Rear helm | $1,069.97 / $1,369.97 | No |

The DIY unit is about **$775 cheaper than a networked 7" Garmin** and about **$1,075 cheaper than a 9"**. The difference buys sonar and radar at the rear helm, IPX7 sealing, a warranty, and no build work.

## DIY Pi unit

### Bench kit (3 carts, priced 2026-10-29)

Everything here except the 6 ft HDMI cable goes on the boat later. Recheck on 2026-10-30: Pi 5 8 GB still $175.00 at Digi-Key, 19,766 in stock.

| Item | Seller | Price |
|---|---|---|
| Raspberry Pi 5, 8 GB (SC1112) | [Digi-Key](https://www.digikey.com/en/products/detail/raspberry-pi/SC1112/21658257) | $175.00 |
| Official Active Cooler (SC1148) | [Digi-Key](https://www.digikey.com/en/products/detail/raspberry-pi/SC1148/21658255) | $5.00 |
| MPD BF353 inline fuse holder | [Digi-Key](https://www.digikey.com/en/products/detail/mpd-memory-protection-devices/BF353/8119223) | $4.14 |
| Littelfuse 0287005.PXCN 5 A ATO fuse | [Digi-Key](https://www.digikey.com/en/products/detail/littelfuse-inc/0287005-PXCN/2519811) | $0.44 |
| **Digi-Key cart** | | **$184.58** ($197.37 with tax and shipping) |
| Waveshare 2-CH isolated CAN HAT+ (27338) | [Amazon](https://www.amazon.com/dp/B0D3GD458Z) | $34.99 |
| Pimoroni NVMe Base (PIM699) | [Amazon](https://www.amazon.com/dp/B0CX754H4D) | $29.99 |
| Netac NV3000 250 GB NVMe SSD | [Amazon](https://www.amazon.com/dp/B0CSSR9PC2) | $49.66 |
| ELNONE USB-C pigtail, 2-pack | [Amazon](https://www.amazon.com/dp/B0CGVNG7Y4) | $7.99 |
| Micro-HDMI to HDMI, 6 ft (bench) + 3 ft (boat) | [Amazon](https://www.amazon.com/dp/B08C2PVP7J) | $13.98 |
| SanDisk Extreme microSD 64 GB (recovery card) | Amazon | $31.99 |
| **Amazon cart** | | **$168.60** ($186.29 with tax and shipping) |
| Pololu D42V55F5.3 step-down regulator | [Pololu](https://www.pololu.com/product/5572) | $47.95 |
| **Pololu cart** | | **$47.95** ($60.66 with tax and shipping) |
| **Bench kit total** | | **$401.13** ($444.32 with tax and shipping) |

Possible cart savings, about $17: the NVMe Base is $19.95 at [Adafruit](https://www.adafruit.com/product/5845), and the 3 ft micro-HDMI cable is not needed if the 4D display is chosen (it takes mini-HDMI, see below).

### Boat parts (priced 2026-10-30)

| Item | Part number | Seller | Price |
|---|---|---|---|
| 4D Systems 4DHDMI 10.1" display: 1000 cd/m2 IPS, 1280x800, touch glass bonded to the panel, USB-C touch, 12 V barrel at 650 mA | 4DHDMI-101-1280-800-CT-EAR-1000 | [Digi-Key](https://www.digikey.com/en/products/detail/4d-systems-pty-ltd/4DHDMI-101-1280-800-CT-EAR-1000/28394428), 4 in stock | $147.95 |
| Micro-HDMI to mini-HDMI cable, 1 ft | ZeniKon B0DP6XCFJ5 | [Amazon](https://www.amazon.com/dp/B0DP6XCFJ5) | $12.99 |
| Hammond 1554 polycarbonate enclosure, 300x200x90 mm, IP66/67/68, NEMA 4X | 1554X2GY | [Digi-Key](https://www.digikey.com/en/products/detail/hammond-manufacturing/1554X2GY/11498222) | $63.22 |
| RAM C-size ball mount, double socket arm | RAM-101U | [RAM Mounts](https://www.rammount.com/part/ram-101u) | $64.49 |
| Pololu Big Pushbutton Power Switch HP (4.5 to 32 V, 6 A at 55 C) | #2813 | [Pololu](https://www.pololu.com/product/2813) | $8.95 |
| EAO 19 mm momentary pushbutton, IP65/IP67 | 82-5751.1000 | Digi-Key | $42.46 |
| Ancor NMEA 2000 drop cable, 1 m (cut, wired to the HAT) | 270301 | [Navstore](https://navstore.com/products/ancor-nmea-2000-drop-cable-1m-270301) | $23.95 |
| Altech PG9 nylon cable gland, IP68, x2 | 5308 509 | Digi-Key | $1.92 |
| Littelfuse TVS diode, 17.1 V standoff | 1.5KE20A | Digi-Key | $1.06 |
| Ancor 16 AWG tinned wire, 25 ft red + 25 ft black | 182803, 182003 | Amazon | $21.93 |
| **Boat parts total** | | | **$388.92** |

Alternatives seen: finished sunlight-readable monitors instead of the bare 4D panel (Beetronics 10HB9M/U1 at $749.00, Xenarc 1029CNH at $770.00), which push the DIY total to about $1,100 with a VESA plate.

### Open questions before buying the boat parts

- **Display input voltage.** The 4D datasheet gives only "12.0 V typ" for the barrel jack, with no maximum. The boat runs about 14.4 V while charging. Ask 4D Systems before ordering.
- **Display power from the buck.** The 4D boards accept 4.8 to 5.2 V over USB. The Pololu outputs 5.3 V, so do not power the display from it.
- **Panel orientation.** 4D's drawing shows a native portrait panel (800x1280). Digi-Key lists 1280x800 over HDMI. Confirm the board outputs landscape.
- **Enclosure depth.** The 16 mm display plus the 45 mm Pi stack is tight inside a 90 mm box. The deeper 1554XA2GY (120 mm) is not priced yet.
- **Tariffs.** Digi-Key shows "tariff may apply" on the Pi, the EAO button, the TVS diode and others. The amount appears only in the cart.

## Second Garmin at the rear helm

The boat is a Hewescraft 240 OceanPro with a hard top and an extended transom. The rear helm is partly covered and about 10 to 20 ft of cable from the main helm.

### Network parts every networked option needs

The 943xsv has **one** Garmin Marine Network port ([spec tab](https://www.garmin.com/en-US/p/697231/pn/010-02366-02/)), and the Fantom 18 radar already uses it. A second networked display therefore needs a GMS 10 network switch at the main helm.

| Part | Part number | Price |
|---|---|---|
| [GMS 10 network port expander](https://www.garmin.com/en-US/p/9706/pn/010-00351-00) (comes with an RJ-45 cable and a power/data cable) | 010-00351-00 | $269.99 |
| [Garmin Marine Network cable, 20 ft](https://www.garmin.com/en-US/p/pn/010-10551-00), GMS 10 to rear helm | 010-10551-00 | $54.99 |
| [NMEA 2000 drop cable, 6 m](https://www.garmin.com/en-US/p/pn/010-11076-01), backbone T to rear helm (replaces the 2 m drop in the box) | 010-11076-01 | $39.99 |
| **Network parts total** | | **$364.97** |

The GPS Store listed the GMS 10 at $209.95 with a 6 ft cable included, about $60 less than Garmin.

### Units

The [x3 GPSMAP](https://www.garmin.com/en-US/p/697231/) boxes include a bail mount, power cable, NMEA 2000 T-connector, a 2 m drop cable, and Garmin Navionics+ charts preloaded.

| Option | Unit | Network parts | Total |
|---|---|---|---|
| GPSMAP 743, 7" (010-02365-60) | $1,199.99 | $364.97 | **$1,564.96** |
| GPSMAP 943, 9" (010-02366-60) | $1,499.99 | $364.97 | **$1,864.96** |
| GPSMAP 1243, 12" (010-02367-60) | $2,899.99 | $364.97 | **$3,164.96** |

The 1243 has two network ports and could be daisy-chained without the GMS 10. That would mean running the radar cable to the rear helm, and Garmin does not clearly say whether a powered-off display passes traffic through, so it is not priced that way here. There is no 10" x3 unit. The 10" GPSMAP 1022 is keyed only (no touch) and comes with a basemap only.

### Not networked, for reference

[ECHOMAP UHD2](https://www.garmin.com/en-US/p/762374/) units cannot join the Garmin Marine Network (Garmin's ECHOMAP installation manual says its network port is not compatible). Like the DIY unit, they show charts and NMEA 2000 data only. Their boxes include no NMEA 2000 T-connector or drop cable.

| Option | Unit | N2K T ($29.99) + 6 m drop ($39.99) | Total |
|---|---|---|---|
| ECHOMAP UHD2 74sv, 7", US Coastal GN+ (010-02685-00) | $999.99 | $69.98 | $1,069.97 |
| ECHOMAP UHD2 94sv, 9", US Coastal GN+ (010-02689-00) | $1,299.99 | $69.98 | $1,369.97 |

### Used market

Unverified (eBay blocked page loads; prices from search results): used 943xsv about $1,000 to $1,200, used 1243xsv about $2,100. A used networked unit still needs the $364.97 in network parts.

## What the difference buys

A networked GPSMAP at the rear helm shows the 943xsv's live sonar and the Fantom radar (with overlay and MARPA) where the owner stands to fish. It also shares waypoints and routes, has its own GPS as a backup, and is IPX7.

The DIY unit can never show Garmin sonar or radar, because those streams are proprietary to the Garmin Marine Network. It fixes the same problem the other way: the new screen takes the chart, so the 943xsv runs full-screen sonar at the main helm. It also gives the fishing chart (NCEI bathymetry, bottom composition), the owner's own software, and room for later layers.
