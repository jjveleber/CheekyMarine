# Test fixtures

- `mixed.log`: hand-written. Candump `-L` lines mixed with a comment, a blank line and an unparseable line, matching the stream test in `test_logfilesource.cpp`.
- `garmin-airmar.log`: converted from canboat `samples/candumpSample1.txt` at tag v9.1.0 (https://raw.githubusercontent.com/canboat/canboat/v9.1.0/samples/candumpSample1.txt), Apache-2.0 licensed. A Garmin 17X GPS, a Garmin GMI-10 and an Airmar DST800 on one bus. The original has no timestamps; `convert_old_candump.py` rewrites each `<0x18eeff01> [8] 05 a0 ...` line as candump `-L` (`(0.002000) can0 18EEFF01#05A0...`), adding 2 ms per frame (so multi-frame fast packets complete well inside the 1 s partial expiry) and dropping comment lines. 6026 frames. Note: every 128267 frame reports depth as not available; only its offset field is valid.

- `ais-static.log`: hand-built (payload from the 129039 test in `test_mappers.cpp`). Identical AIS class B position reports for MMSI 338123456 as 4-frame fast packets at 1 s to 8 s, then one ISO request frame at 1000 s so the target expires on the replay clock.

Regenerate `garmin-airmar.log` with `python3 n2kd/tests/fixtures/convert_old_candump.py candumpSample1.txt n2kd/tests/fixtures/garmin-airmar.log`.

Any further canboat sample files are Apache-2.0 licensed and must be listed here with their origin.
