"""Synthetic NMEA 2000 candump log generator for the plotter's dev runs and tests.

The encoder is generic: it packs field values using the field layout (BitOffset, BitLength,
Resolution, Signed) of the PGN in canboat.json, so the log exercises n2kd's real decode path.
Unset fields, including reserved ones, are all ones (not available); unset signed fields are the
largest positive value instead, which is how a signed field reads not available.

Usage: synth_n2k.py --canboat PATH --out FILE [--scenario NAME] [--duration-s N] [--ais-csv PATH]
Scenarios: everett-pt-townsend, navigating, fishing, fishing-stopped, ais-density (real Puget Sound
traffic from tests/fixtures/ais/; --ais-csv overrides the file).
Python stdlib only; deterministic (same bytes every run).
"""
import argparse
import csv
import json
import math
import os
import sys

T0 = 1798000000.0  # 2026-12-23 UTC, fixed so tests are deterministic
DURATION_S = 1200  # 20 minutes
T0_DAY = 1798056000.0  # 2026-12-23 20:00 UTC, noon PST: the auto palette picks day
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
            if bits > 0 and f.get("Signed") and f["Id"] not in values:
                # A signed field's not-available pattern is the largest positive value, not all ones.
                mask = ((1 << bits) - 1) << f["BitOffset"]
                word = (word & ~mask) | (((1 << (bits - 1)) - 1) << f["BitOffset"])
                continue
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
    """Constant-speed travel along waypoints (lat, lon) on a flat-earth approximation.

    With bounce the boat turns back at the route end and retraces it (course reversed), repeatedly;
    without, it carries on along the last leg's line."""

    def __init__(self, waypoints, speed, bounce=False):
        self.wp = waypoints
        self.speed = speed
        self.bounce = bounce
        self.legs = [_bearing_and_len(a, b) for a, b in zip(waypoints, waypoints[1:])]
        self.total = sum(ln for _, ln in self.legs)

    def _folded(self, s):
        """(distance along the route, going back)."""
        dist = self.speed * s
        if not self.bounce:
            return dist, False
        dist %= 2 * self.total
        return (2 * self.total - dist, True) if dist > self.total else (dist, False)

    def fraction(self, s):
        """Distance along the route over its length, folded by the bounce."""
        return self._folded(s)[0] / self.total

    def at(self, s):
        """(lat, lon, course_rad) after s seconds; the last leg's course past the end."""
        dist, back = self._folded(s)
        for i, (brg, ln) in enumerate(self.legs):
            if dist <= ln or i == len(self.legs) - 1:
                a, b = self.wp[i], self.wp[i + 1]
                f = dist / ln
                if back:
                    brg = (brg + math.pi) % (2 * math.pi)
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, brg
            dist -= ln


def offset_position(origin, east_m, north_m):
    lat = origin[0] + north_m / M_PER_DEG
    return lat, origin[1] + east_m / (M_PER_DEG * math.cos(math.radians(origin[0])))


def depth_m(s):
    return 30 + 25 * math.sin(2 * math.pi * s / 300)


WAYPOINTS = [(47.9800, -122.2300), (47.9900, -122.3000), (48.0500, -122.4500), (48.1100, -122.7500)]
SPEED = 3.0866  # m/s, about 6 kn


def ais_targets(emit, own, duration, names):
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
    for mmsi, cls, side, ahead, kn, phase in targets:
        for s in range(phase, duration, 10):
            d = ahead + kn * KN * s
            lat, lon = offset_position(own.wp[0], side * right[0] + d * fwd[0], side * right[1] + d * fwd[1])
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


def everett_pt_townsend(enc, duration=DURATION_S):
    """List of (time, order, frame) for the scenario."""
    wp = WAYPOINTS
    own = Track(wp, SPEED)
    ev = []

    def emit(s_ms, pgn, src, prio, values):
        for can_id, data in enc.frames(pgn, src, prio, values):
            ev.append((s_ms, len(ev), can_id, data))

    for s in range(duration):
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

    ais_targets(emit, own, duration, {367000001: "TEST TUG", 367000002: "TEST SAIL"})
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


NAV_WAYPOINTS = [(47.9482896, -122.3136073), (47.9021326, -122.3743223), (47.9080896, -122.4492273)]
NAV_SPEED = 26 * KN
FISH_WAYPOINTS = [(47.7441216, -122.4728663), (47.7444076, -122.4562403)]
FISH_SPEED = 3 * 0.44704  # 3 mph in m/s
VARIATION = 0.2731
NAV_DEPTHS = [(0, 8), (0.3, 90), (0.55, 120), (0.8, 20), (1.0, 60)]


def interp(table, x):
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def own_ship(enc, duration, pos, heading, sog, depth, temp):
    """Own ship at 1 Hz: pos(s) -> (lat, lon, cog), heading(s, cog), sog(s), depth(s); no dropouts."""
    ev = []

    def emit(s_ms, pgn, src, prio, values):
        for can_id, data in enc.frames(pgn, src, prio, values):
            ev.append((s_ms, len(ev), can_id, data))

    for s in range(duration):
        ms = s * 1000
        sid = s % 253
        lat, lon, cog = pos(s)
        emit(ms, 129025, 1, 2, {"latitude": lat, "longitude": lon})
        emit(ms, 129026, 1, 2, {"sid": sid, "cogReference": 0, "cog": cog, "sog": sog(s)})
        emit(ms, 127250, 1, 2, {"sid": sid, "heading": heading(s, cog) % (2 * math.pi),
                                "variation": VARIATION, "reference": 1})
        emit(ms, 128267, 1, 3, {"sid": sid, "depth": depth(s), "offset": -0.3})
        if s % 2 == 0:
            emit(ms, 130316, 1, 5, {"sid": sid, "instance": 0, "source": 0, "temperature": temp})
    return ev, emit


def navigating(enc, duration=960):
    own = Track(NAV_WAYPOINTS, NAV_SPEED, bounce=True)
    ev, emit = own_ship(
        enc, duration, own.at,
        lambda s, cog: cog - VARIATION + 0.03 * math.sin(2 * math.pi * s / 7),
        lambda s: NAV_SPEED + 0.5 * KN * math.sin(2 * math.pi * s / 11),
        lambda s: interp(NAV_DEPTHS, own.fraction(s)) + 0.3 * math.sin(2 * math.pi * s / 5),
        283.15)
    ais_targets(emit, own, duration, {367000001: "TEST TUG", 367000002: "TEST SAIL"})
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


def fishing_own(enc, duration):
    own = Track(FISH_WAYPOINTS, FISH_SPEED, bounce=True)
    return own_ship(
        enc, duration, own.at, lambda s, cog: cog - VARIATION, lambda s: FISH_SPEED,
        lambda s: 27.5 + 12.5 * math.cos(2 * math.pi * own.fraction(s)) + 0.2 * math.sin(2 * math.pi * s / 8),
        284.15)


def fishing(enc, duration=1860):
    ev, emit = fishing_own(enc, duration)
    # One class A ferry, 800 m east and 2 km north of the start, steaming 200 deg true at 12 kn.
    course = math.radians(200)
    for s in range(0, duration, 10):
        d = 12 * KN * s
        lat, lon = offset_position(FISH_WAYPOINTS[0], 800 + d * math.sin(course), 2000 + d * math.cos(course))
        emit(s * 1000, 129038, 2, 4, {"userId": 367000011, "latitude": lat, "longitude": lon,
                                      "cog": course, "sog": 12 * KN, "heading": course, "timeStamp": s % 60,
                                      "messageId": 1, "navStatus": 0, "aisTransceiverInformation": 0})
        if s % 60 == 0:
            emit(s * 1000, 129794, 2, 6, {"userId": 367000011, "name": "TEST FERRY",
                                          "aisTransceiverInformation": 0, "messageId": 5, "typeOfShip": 60})
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


AIS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tests", "fixtures", "ais", "puget-2024-07-13.csv")


def ais_density(enc, duration=1800, ais_csv=None):
    """Own ship as in fishing, plus the real Puget Sound traffic of the MarineCadastre extract."""
    ev, emit = fishing_own(enc, duration)
    seen = set()
    with open(ais_csv or AIS_CSV, encoding="ascii", newline="") as f:
        for row in csv.DictReader(f):
            ms = int(round(float(row["t"]) * 1000))
            if ms >= duration * 1000:
                continue
            mmsi = int(row["mmsi"])
            cls = "B" if row["cls"] == "B" else "A"
            kin = {"userId": mmsi, "latitude": float(row["lat"]), "longitude": float(row["lon"]),
                   "timeStamp": (ms // 1000) % 60, "aisTransceiverInformation": 0}
            if row["sog_kn"]:
                kin["sog"] = float(row["sog_kn"]) * KN
            if row["cog"]:
                kin["cog"] = math.radians(float(row["cog"]))
            if row["heading"] and int(row["heading"]) != 511:
                kin["heading"] = math.radians(int(row["heading"]))
            if cls == "A":
                kin.update({"messageId": 1, "navStatus": 0})
                emit(ms, 129038, 2, 4, kin)
            else:
                kin["messageId"] = 18
                emit(ms, 129039, 2, 4, kin)
            if mmsi not in seen:
                seen.add(mmsi)
                st = {"userId": mmsi, "name": row["name"], "aisTransceiverInformation": 0}
                if cls == "A":
                    st["messageId"] = 5
                    if row["type"]:
                        st["typeOfShip"] = int(row["type"])
                    emit(ms, 129794, 2, 6, st)
                else:
                    st["messageId"] = 24
                    emit(ms, 129809, 2, 6, st)
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


def fishing_stopped(enc, duration=600):
    o = FISH_WAYPOINTS[0]

    def pos(s):
        lat, lon = offset_position(o, 1.2 * math.sin(0.7 * s), 1.2 * math.cos(0.9 * s))
        return lat, lon, 0.0

    ev, _ = own_ship(enc, duration, pos, lambda s, cog: cog - VARIATION, lambda s: 0.0, lambda s: 12.0, 284.15)
    ev.sort(key=lambda e: (e[0], e[1]))
    return ev


# name -> (function, start time, default duration in seconds)
SCENARIOS = {
    "everett-pt-townsend": (everett_pt_townsend, T0, DURATION_S),
    "navigating": (navigating, T0_DAY, 960),
    "fishing": (fishing, T0_DAY, 1860),
    "fishing-stopped": (fishing_stopped, T0_DAY, 600),
    "ais-density": (ais_density, T0_DAY, 1800),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--canboat", required=True, help="path to canboat.json")
    ap.add_argument("--out", required=True, help="candump log file to write")
    ap.add_argument("--scenario", default="everett-pt-townsend", choices=sorted(SCENARIOS))
    ap.add_argument("--duration-s", type=int, help="scenario length in seconds (default per scenario)")
    ap.add_argument("--ais-csv", help="ais-density: traffic CSV (default: the committed fixture)")
    args = ap.parse_args(argv)
    fn, t0, default_s = SCENARIOS[args.scenario]
    kw = {"ais_csv": args.ais_csv} if args.scenario == "ais-density" else {}
    events = fn(Encoder(args.canboat), args.duration_s or default_s, **kw)
    with open(args.out, "w", encoding="ascii", newline="\n") as f:
        for ms, _, can_id, data in events:
            f.write("(%.6f) can0 %08X#%s\n" % (t0 + ms / 1000.0, can_id, data.hex().upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
