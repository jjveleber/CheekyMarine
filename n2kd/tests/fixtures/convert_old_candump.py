# Convert old candump lines "<0x18eeff01> [8] 05 a0 ..." to candump -L form
# "(0.100000) can0 18EEFF01#05A0...". Usage: python3 convert_old_candump.py IN OUT
import re, sys
pat = re.compile(r"^<0x([0-9a-fA-F]+)> \[(\d)\]((?: [0-9a-fA-F]{2})*)\s*$")
n = 0
with open(sys.argv[1]) as src, open(sys.argv[2], "w") as dst:
    for line in src:
        m = pat.match(line)
        if m:
            n += 1
            dst.write(f"({n // 10}.{n % 10}00000) can0 {int(m[1], 16):08X}#{m[3].replace(' ', '').upper()}\n")
