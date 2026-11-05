"""Moves a recorded NMEA 2000 log onto other waters by rewriting its positions.

Reads a candump -L log ("(ts) iface ID#HEX") or a canboat RAW log ("ts,prio,pgn,src,dst,len,b0,..."),
translates every position so the first own-ship position (PGN 129025 or 129029) lands on --to, then
optionally rotates the whole track clockwise (compass sense) about --to. Positions are the latitude
and longitude fields of PGNs 129025, 129029, 129038 and 129039, located through canboat.json.
Frames of other PGNs and frames that do not form a message (an incomplete fast packet) pass through
unchanged, in place. Output is a candump -L log with the input timestamps (RAW times are UTC).

Usage: relocate_n2k.py IN OUT --to LAT,LON [--rotate DEG] --canboat PATH
Python stdlib only.
"""
import argparse
import calendar
import json
import math
import re
import sys
from collections import namedtuple

M_PER_DEG = 111194.9  # per degree of latitude, spherical earth R = 6371 km (as synth_n2k.py)
POSITION_PGNS = (129025, 129029, 129038, 129039)
ORIGIN_PGNS = (129025, 129029)
FAST_PGNS = (129029, 129038, 129039)

# payload is None for a frame that does not form a message; frames are the original (ts, can_id, data).
Message = namedtuple("Message", "ts can_id src pgn payload frame_indexes frames")

_CANDUMP = re.compile(r"^\(([0-9.]+)\)\s+\S+\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)$")
_STAMP = re.compile(r"^(\d{4})-(\d\d)-(\d\d)[-TZ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z?$")


def _parse_stamp(s):
    m = _STAMP.match(s)
    if not m:
        return None
    y, mo, d, h, mi, sec = (int(g) for g in m.groups()[:6])
    frac = float("0." + m.group(7)) if m.group(7) else 0.0
    return calendar.timegm((y, mo, d, h, mi, sec)) + frac


def _parse_raw(line):
    f = line.split(",")
    if len(f) < 6:
        return None
    try:
        ts = _parse_stamp(f[0])
        prio, pgn, src, dst, n = (int(x) for x in f[1:6])
        if ts is None or n > 8 or len(f) < 6 + n or any(len(x) != 2 for x in f[6:6 + n]):
            return None
        data = bytes(int(x, 16) for x in f[6:6 + n])
    except ValueError:
        return None
    if (pgn >> 8) & 0xFF < 240:  # PDU1: destination in the PS byte
        pgn |= dst
    return ts, (prio << 26) | (pgn << 8) | src, data


def read_frames(path):
    """[(ts, can_id, data)] from a candump -L or canboat RAW file; unparseable lines are skipped."""
    out = []
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = _CANDUMP.match(line)
            if m:
                out.append((float(m.group(1)), int(m.group(2), 16), bytes.fromhex(m.group(3))))
                continue
            fr = _parse_raw(line)
            if fr:
                out.append(fr)
    return out


def _pgn_of(can_id):
    pgn = (can_id >> 8) & 0x1FFFF
    if (pgn >> 8) & 0xFF < 240:  # PDU1: the low byte is the destination, not part of the PGN
        pgn &= 0x1FF00
    return pgn


def reassemble(frames):
    """Messages covering every frame, in order of their first frame. Fast packets (by source, PGN
    and sequence) are joined; other frames are single-frame messages; frames of a fast packet that
    never completes each become a message with payload None."""
    msgs = []
    pending = {}  # (src, pgn) -> [seq, total, data, indexes, next frame number]

    def single(i, payload):
        ts, can_id, data = frames[i]
        msgs.append(Message(ts, can_id, can_id & 0xFF, _pgn_of(can_id), payload, (i,), (frames[i],)))

    def drop(key):
        for i in pending.pop(key)[3]:
            single(i, None)

    for i, (ts, can_id, data) in enumerate(frames):
        pgn = _pgn_of(can_id)
        if pgn not in FAST_PGNS:
            single(i, data)
            continue
        key = (can_id & 0xFF, pgn)
        if not data:
            if key in pending:
                drop(key)
            single(i, None)
            continue
        seq, num = data[0] >> 5, data[0] & 0x1F
        if num == 0:
            if key in pending:
                drop(key)
            if len(data) < 2:
                single(i, None)
                continue
            pending[key] = [seq, data[1], bytearray(data[2:]), [i], 1]
        else:
            p = pending.get(key)
            if p is None or p[0] != seq or p[4] != num:
                if p is not None:
                    drop(key)
                single(i, None)
                continue
            p[2].extend(data[1:])
            p[3].append(i)
            p[4] += 1
        p = pending[key]
        if len(p[2]) >= p[1]:
            del pending[key]
            idx = tuple(p[3])
            msgs.append(Message(frames[idx[0]][0], can_id, key[0], pgn, bytes(p[2][:p[1]]), idx,
                                tuple(frames[j] for j in idx)))
    for key in list(pending):
        drop(key)
    msgs.sort(key=lambda m: m.frame_indexes[0])
    return msgs


def transform(lat, lon, origin, to, rotate_deg):
    """Translate so origin lands on to, then rotate about to clockwise by rotate_deg (flat earth)."""
    lat += to[0] - origin[0]
    lon += to[1] - origin[1]
    if not rotate_deg:
        return lat, lon
    k = M_PER_DEG * math.cos(math.radians(to[0]))
    east, north = (lon - to[1]) * k, (lat - to[0]) * M_PER_DEG
    a = math.radians(rotate_deg)
    e2 = east * math.cos(a) + north * math.sin(a)
    n2 = north * math.cos(a) - east * math.sin(a)
    return to[0] + n2 / M_PER_DEG, to[1] + e2 / k


def _layouts(canboat):
    with open(canboat, encoding="utf-8") as f:
        pgns = {p["PGN"]: p for p in json.load(f)["PGNs"]}
    out = {}
    for n in POSITION_PGNS:
        fields = {f["Id"]: f for f in pgns[n]["Fields"] if f["Id"] in ("latitude", "longitude")}
        out[n] = (fields["latitude"], fields["longitude"])
    return out


def _get(payload, f):
    """Field value, or None when it is not available or lies beyond the payload."""
    bits, off = f["BitLength"], f["BitOffset"]
    if off + bits > 8 * len(payload):
        return None
    raw = (int.from_bytes(payload, "little") >> off) & ((1 << bits) - 1)
    if raw == (1 << bits) - 1:  # all ones: not available (as a signed value it is only -1 LSB)
        return None
    if f.get("Signed"):
        if raw == (1 << (bits - 1)) - 1:  # signed largest positive: not available
            return None
        if raw >> (bits - 1):
            raw -= 1 << bits
    return raw * f.get("Resolution", 1)


def _set(payload, f, value):
    bits, off = f["BitLength"], f["BitOffset"]
    raw = int(round(value / f.get("Resolution", 1)))
    if not -(1 << (bits - 1)) < raw < (1 << (bits - 1)) - 1:
        raise ValueError("position out of range for field " + f["Id"])
    word = int.from_bytes(payload, "little")
    word = (word & ~(((1 << bits) - 1) << off)) | ((raw & ((1 << bits) - 1)) << off)
    return word.to_bytes(len(payload), "little")


def _position(msg, layouts):
    """(lat, lon) of a position message, or None when absent or not available."""
    if msg.payload is None or msg.pgn not in layouts:
        return None
    flat, flon = layouts[msg.pgn]
    lat, lon = _get(msg.payload, flat), _get(msg.payload, flon)
    return None if lat is None or lon is None else (lat, lon)


def _lay(frames, payload):
    """The frames with payload laid over their data bytes; framing bytes and padding are kept."""
    if len(frames) == 1:
        return [(frames[0][0], frames[0][1], payload)]
    out, pos = [], 0
    for n, (ts, can_id, data) in enumerate(frames):
        head = 2 if n == 0 else 1
        take = min(len(data) - head, len(payload) - pos)
        out.append((ts, can_id, data[:head] + payload[pos:pos + take] + data[head + take:]))
        pos += take
    return out


def relocate(messages, to, rotate_deg, canboat):
    """Frames of the messages with every available position moved, in original order."""
    layouts = _layouts(canboat)
    origin = next((p for p in (_position(m, layouts) for m in messages if m.pgn in ORIGIN_PGNS) if p), None)
    out = []
    for m in messages:
        pos = _position(m, layouts) if origin else None
        if pos is None:
            out.extend(zip(m.frame_indexes, m.frames))
            continue
        flat, flon = layouts[m.pgn]
        lat, lon = transform(pos[0], pos[1], origin, to, rotate_deg)
        payload = _set(_set(m.payload, flat, lat), flon, lon)
        out.extend(zip(m.frame_indexes, _lay(m.frames, payload)))
    out.sort(key=lambda p: p[0])
    return [fr for _, fr in out]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--to", required=True, help="LAT,LON the first own-ship position moves to")
    ap.add_argument("--rotate", type=float, default=0.0, help="degrees clockwise about --to (default 0)")
    ap.add_argument("--canboat", required=True, help="path to canboat.json")
    args = ap.parse_args(argv)
    try:
        lat, lon = (float(x) for x in args.to.split(","))
    except ValueError:
        ap.error("--to wants LAT,LON")
    messages = reassemble(read_frames(args.input))
    layouts = _layouts(args.canboat)
    if not any(_position(m, layouts) for m in messages if m.pgn in ORIGIN_PGNS):
        print("no own-ship position (129025 or 129029): nothing moved", file=sys.stderr)
        return 1
    try:
        out = relocate(messages, (lat, lon), args.rotate, args.canboat)
    except ValueError as e:  # a moved position past its field's range
        print("error: %s" % e, file=sys.stderr)
        return 1
    with open(args.output, "w", encoding="ascii", newline="\n") as f:
        for ts, can_id, data in out:
            f.write("(%.6f) can0 %08X#%s\n" % (ts, can_id, data.hex().upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
