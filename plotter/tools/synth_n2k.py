"""Synthetic NMEA 2000 candump log generator for the plotter's dev runs and tests.

The encoder is generic: it packs field values using the field layout (BitOffset, BitLength,
Resolution, Signed) of the PGN in canboat.json, so the log exercises n2kd's real decode path.
Unset fields, including reserved ones, are all ones (not available).

Usage: synth_n2k.py --canboat PATH --out FILE [--scenario everett-pt-townsend]
Python stdlib only; deterministic (same bytes every run).
"""
import argparse
import json
import math
import sys

T0 = 1798000000.0  # 2026-12-23 UTC, fixed so tests are deterministic
DURATION_S = 1200  # 20 minutes
KN = 1852.0 / 3600.0
M_PER_DEG = 111194.9  # per degree of latitude, spherical earth R = 6371 km


class Encoder:
    def __init__(self, canboat_path):
        with open(canboat_path, encoding="utf-8") as f:
            self.pgns = {p["PGN"]: p for p in json.load(f)["PGNs"]}
        self.fast_seq = {}

    def payload(self, pgn, values):
        """Pack values (field Id -> number or str) into the PGN's payload bytes."""
        d = self.pgns[pgn]
        length = d["Length"]
        word = (1 << (8 * length)) - 1  # all ones
        for f in d["Fields"]:
            bits = f.get("BitLength", 0)
            if f["Id"] not in values or bits <= 0:
                continue
            v = values[f["Id"]]
            if isinstance(v, str):
                data = v.encode("ascii")[: bits // 8]
                raw = int.from_bytes(data + b"\xff" * (bits // 8 - len(data)), "little")
            else:
                raw = int(round(v / f.get("Resolution", 1)))
                if f.get("Signed"):
                    if not -(1 << (bits - 1)) <= raw < (1 << (bits - 1)):
                        raise ValueError("value out of range for field " + f["Id"])
                    raw &= (1 << bits) - 1
                elif not 0 <= raw < (1 << bits):
                    raise ValueError("value out of range for field " + f["Id"])
                if raw == (1 << bits) - 1:
                    raise ValueError("value is the not-available pattern for field " + f["Id"])
            mask = ((1 << bits) - 1) << f["BitOffset"]
            word = (word & ~mask) | (raw << f["BitOffset"])
        return word.to_bytes(length, "little")

    def frames(self, pgn, src, prio, values):
        """CAN id and data of each frame carrying the PGN (fast packet when over 8 bytes)."""
        data = self.payload(pgn, values)
        can_id = (prio << 26) | (pgn << 8) | src
        if len(data) <= 8:
            return [(can_id, data.ljust(8, b"\xff") if len(data) < 8 else data)]
        seq = self.fast_seq.get((src, pgn), 0)
        self.fast_seq[(src, pgn)] = (seq + 1) & 7
        out = [(can_id, bytes([seq << 5, len(data)]) + data[:6])]
        rest = data[6:]
        for n in range(1, 1 + (len(rest) + 6) // 7):
            chunk = rest[(n - 1) * 7 : n * 7]
            out.append((can_id, bytes([seq << 5 | n]) + chunk.ljust(7, b"\xff")))
        return out


def _bearing_and_len(a, b):
    dy = (b[0] - a[0]) * M_PER_DEG
    dx = (b[1] - a[1]) * M_PER_DEG * math.cos(math.radians(a[0]))
    return math.atan2(dx, dy) % (2 * math.pi), math.hypot(dx, dy)


class Track:
    """Constant-speed travel along waypoints (lat, lon) on a flat-earth approximation."""

    def __init__(self, waypoints, speed):
        self.wp = waypoints
        self.speed = speed
        self.legs = [_bearing_and_len(a, b) for a, b in zip(waypoints, waypoints[1:])]

    def at(self, s):
        """(lat, lon, course_rad) after s seconds; the last leg's course past the end."""
        dist = self.speed * s
        for i, (brg, ln) in enumerate(self.legs):
            if dist <= ln or i == len(self.legs) - 1:
                a, b = self.wp[i], self.wp[i + 1]
                f = dist / ln
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, brg
            dist -= ln


def offset_position(origin, east_m, north_m):
    lat = origin[0] + north_m / M_PER_DEG
    return lat, origin[1] + east_m / (M_PER_DEG * math.cos(math.radians(origin[0])))


def depth_m(s):
    return 30 + 25 * math.sin(2 * math.pi * s / 300)


def everett_pt_townsend(enc):
    """List of (time, order, frame) for the scenario."""
    wp = [(47.9800, -122.2300), (47.9900, -122.3000), (48.0500, -122.4500), (48.1100, -122.7500)]
    own = Track(wp, 3.0866)
    ev = []

    def emit(s_ms, pgn, src, prio, values):
        for can_id, data in enc.frames(pgn, src, prio, values):
            ev.append((s_ms, len(ev), can_id, data))

    for s in range(DURATION_S):
        ms = s * 1000
        sid = s % 253
        lat, lon, cog = own.at(s)
        if not 300 <= s < 315:
            emit(ms, 129025, 1, 2, {"latitude": lat, "longitude": lon})
            emit(ms, 129026, 1, 2, {"sid": sid, "cogReference": 0, "cog": cog, "sog": own.speed})
        emit(ms, 127250, 1, 2, {"sid": sid, "heading": (cog + 0.05) % (2 * math.pi),
                                "variation": 0.2731, "reference": 1})
        if not 360 <= s < 372:
            emit(ms, 128267, 1, 3, {"sid": sid, "depth": depth_m(s), "offset": -0.3})
        if s % 2 == 0:
            emit(ms, 130316, 1, 5, {"sid": sid, "instance": 0, "source": 0, "temperature": 283.15})

    # AIS targets travel along the first leg's bearing, offset sideways from the own ship's track
    # (starboard positive): 1.5 km, 1.2 km and 1.8 km, at 6, 4 and 8 kn.
    brg = own.legs[0][0]
    right = (math.cos(brg), -math.sin(brg))  # unit vector to starboard (east, north)
    fwd = (math.sin(brg), math.cos(brg))
    targets = [  # mmsi, class, offset m (starboard +), start ahead m, speed kn, phase s
        (367000001, "A", 1500.0, 500.0, 6.0, 0),
        (367000002, "B", -1200.0, -300.0, 4.0, 3),
        (367000003, "A", 1800.0, 1000.0, 8.0, 6),
    ]
    names = {367000001: "TEST TUG", 367000002: "TEST SAIL"}
    for mmsi, cls, side, ahead, kn, phase in targets:
        for s in range(phase, DURATION_S, 10):
            d = ahead + kn * KN * s
            lat, lon = offset_position(wp[0], side * right[0] + d * fwd[0], side * right[1] + d * fwd[1])
            kin = {"userId": mmsi, "latitude": lat, "longitude": lon, "cog": brg, "sog": kn * KN,
                   "heading": brg, "timeStamp": s % 60}
            ms = s * 1000
            if cls == "A":
                kin.update({"messageId": 1, "navStatus": 0, "aisTransceiverInformation": 0})
                emit(ms, 129038, 2, 4, kin)
            else:
                kin.update({"messageId": 18, "aisTransceiverInformation": 0})
                emit(ms, 129039, 2, 4, kin)
            if mmsi in names:
                st = {"userId": mmsi, "name": names[mmsi], "aisTransceiverInformation": 0}
                if cls == "A":
                    st.update({"messageId": 5, "typeOfShip": 31})
                    emit(ms, 129794, 2, 6, st)
                else:
                    st.update({"messageId": 24})
                    emit(ms, 129809, 2, 6, st)
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


SCENARIOS = {"everett-pt-townsend": everett_pt_townsend}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--canboat", required=True, help="path to canboat.json")
    ap.add_argument("--out", required=True, help="candump log file to write")
    ap.add_argument("--scenario", default="everett-pt-townsend", choices=sorted(SCENARIOS))
    args = ap.parse_args(argv)
    events = SCENARIOS[args.scenario](Encoder(args.canboat))
    with open(args.out, "w", encoding="ascii", newline="\n") as f:
        for ms, _, can_id, data in events:
            f.write("(%.6f) can0 %08X#%s\n" % (T0 + ms / 1000.0, can_id, data.hex().upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
