# Pi 5 bench dev kit

Prices checked 2026-10-29 on the product pages (US, before tax and shipping). "Unverified" means seen only in a search listing. Prices move often; recheck before ordering.

Purpose: run the plotter on real hardware under EGLFS (plan 3 Task 18) and start NMEA 2000 bench work, before the panel, power and enclosure are chosen in plan 5. Everything here except the bench-only items goes on the boat later.

## Price warning

Memory shortages have raised Raspberry Pi prices several times since launch: Pi 5 8 GB was $80 at launch and is $175 at retail today. The parent spec's shopping list (section 7) assumed $80. The under-$1000 total still holds, but the margin is about $95 smaller. NVMe SSDs are short too: the official Raspberry Pi SSDs are out of stock at every US reseller checked.

## Recommended kit (one PiShop order)

| Item | Price | Link | Later use |
|---|---|---|---|
| Raspberry Pi 5, 8 GB (SC1112) | $175.00 | <https://www.pishop.us/product/raspberry-pi-5-8gb/> | boat |
| Official Active Cooler (SC1148) | $12.95 | <https://www.pishop.us/product/raspberry-pi-active-cooler/> | boat |
| Official 27W USB-C power supply, US | $12.95 | <https://www.pishop.us/product/raspberry-pi-27w-usb-c-power-supply-black-us/> | bench only |
| Official microSD 64 GB A2, Pi OS preloaded | $20.95 | <https://www.pishop.us/product/official-raspberry-pi-microsd-card-with-raspberry-pi-os-64-bit-64gb/> | recovery card |
| Micro-HDMI to HDMI cable, 1 m | $6.95 | <https://www.pishop.us/product/micro-hdmi-to-standard-hdmi-a-m-1m-cable-black/> | bench only |
| **Total** | **$228.80** | | |

Use any HDMI monitor already at hand: HDMI is the most proven EGLFS path. Reflash the card with Raspberry Pi OS trixie Lite 64-bit.

Same board at CanaKit: $175.00, <https://www.canakit.com/raspberry-pi-5-8gb.html>

## Options

- **Pi 5 4 GB instead of 8 GB:** $110.00 at PiShop (unverified), saves $65. Qt, MapLibre and n2kd should fit in 4 GB; 8 GB is headroom. The 16 GB at $305 is not worth it.
- **Touch display for touch testing:** Raspberry Pi Touch Display 2, 7 in, $81.95, <https://www.pishop.us/product/raspberry-pi-touch-display-2/> . DSI, auto-detected on the Pi 5. Portrait native (720x1280), so the app or the Qt KMS config must rotate it. It takes 5 V from GPIO pins, which conflicts with a CAN HAT on the header unless a stacking header is used. Brings the kit to $310.75.
- **Cheap CAN for bench loopback:** Waveshare 2-Channel Isolated CAN Bus HAT+ (27338), $28.95, <https://www.pishop.us/product/2-channel-isolated-can-bus-hat-for-raspberry-pi/> . Pi 5 listed as supported, screw terminals (no Micro-C). Wiring can0 to can1 replays NMEA 2000 traffic without a real bus.

## Buy later

- **PiCAN-M without SMPS** (boat NMEA 2000 interface, parent spec section 7): $99.95, <https://copperhilltech.com/pican-m-nmea-0183-nmea-2000-hat-for-raspberry-pi/> . Separate Copperhill order. Pi 5 support is likely but not stated by the vendor: Copperhill's Pi 5 test covered the PiCAN Duo with the standard MCP2515 overlays. Ask Copperhill before ordering.
- **NVMe storage:** Pimoroni NVMe Base (PIM699, mounts under the Pi so the GPIO header stays free for the CAN HAT), $18.95, <https://www.pishop.us/product/nvme-base-for-raspberry-pi-5-nvme-base/> ; official M.2 HAT+ $12.00. Buy the SSD when stock returns (official 256 GB listed at $145.00, out of stock). Bench work runs fine from microSD.
- **Case:** skip on the bench; an open board is easier for stacking HATs.
