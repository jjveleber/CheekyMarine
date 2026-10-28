# Test fixtures

- `mixed.log`: hand-written. Candump `-L` lines mixed with a comment, a blank line and an unparseable line, matching the stream test in `test_logfilesource.cpp`.
- `garmin-airmar.log`: converted from canboat `samples/candumpSample1.txt` at tag v9.1.0 (https://raw.githubusercontent.com/canboat/canboat/v9.1.0/samples/candumpSample1.txt), Apache-2.0 licensed. A Garmin 17X GPS, a Garmin GMI-10 and an Airmar DST800 on one bus. The original has no timestamps; `convert_old_candump.py` rewrites each `<0x18eeff01> [8] 05 a0 ...` line as candump `-L` (`(0.100000) can0 18EEFF01#05A0...`), adding 0.1 s per frame and dropping comment lines. 6026 frames. Note: every 128267 frame reports depth as not available; only its offset field is valid.

Regenerate with `python3 n2kd/tests/fixtures/convert_old_candump.py candumpSample1.txt n2kd/tests/fixtures/garmin-airmar.log`.

Any further canboat sample files are Apache-2.0 licensed and must be listed here with their origin.
