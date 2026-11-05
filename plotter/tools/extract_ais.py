"""Extracts a window of real AIS traffic from a MarineCadastre daily GeoParquet into a small CSV.

Needs pyarrow (this is the only tool here that does; run it once, the CSV is committed).
Usage: extract_ais.py --parquet FILE --bbox W,S,E,N --start ISO --end ISO --out CSV [--thin-s 20]
Columns: mmsi,t,lat,lon,sog_kn,cog,heading,name,type,length,cls
t is seconds from --start (one decimal); one row per vessel per --thin-s seconds.
Heading 511 (not available) and empty values become empty fields; names are ASCII only.
Source columns: MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, VesselType, Length,
TransceiverClass.
"""
import argparse
import csv
import datetime
import struct
import sys

import pyarrow.parquet as pq

COLS = ["mmsi", "base_date_time", "geometry", "sog", "cog", "heading", "vessel_name", "vessel_type",
        "length", "transceiver"]


def lonlat(wkb):
    """(lon, lat) of a WKB point (little endian, 2D)."""
    if wkb[0] != 1:
        raise ValueError("unexpected WKB byte order")
    return struct.unpack_from("<dd", wkb, 5)


def parse_iso(s):
    return datetime.datetime.fromisoformat(s).replace(tzinfo=None)


def clean(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return v


def ascii_name(v):
    v = clean(v)
    return "".join(c if 32 <= ord(c) < 127 and c != "," else "?" for c in str(v).strip())


def num(v, nd):
    v = clean(v)
    return "" if v == "" else ("%.*f" % (nd, v)).rstrip("0").rstrip(".") if nd else str(int(v))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--bbox", required=True, help="W,S,E,N in degrees")
    ap.add_argument("--start", required=True, help="ISO UTC, e.g. 2024-07-13T20:00:00")
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thin-s", type=float, default=20)
    args = ap.parse_args(argv)
    w, s, e, n = (float(x) for x in args.bbox.split(","))
    t0, t1 = parse_iso(args.start), parse_iso(args.end)
    table = pq.read_table(args.parquet, columns=COLS, filters=[
        ("base_date_time", ">=", t0), ("base_date_time", "<", t1)])
    rows = []
    for r in table.to_pylist():
        r["lon"], r["lat"] = lonlat(r["geometry"])
        if w <= r["lon"] <= e and s <= r["lat"] <= n:
            rows.append(r)
    rows.sort(key=lambda r: (r["mmsi"], r["base_date_time"]))
    last = {}
    out = []
    for r in rows:
        t = (r["base_date_time"] - t0).total_seconds()
        m = r["mmsi"]
        if m in last and t - last[m] < args.thin_s:
            continue
        last[m] = t
        hd = clean(r["heading"])
        out.append((t, [m, "%.1f" % t, "%.5f" % r["lat"], "%.5f" % r["lon"], num(r["sog"], 1),
                        num(r["cog"], 1), "" if hd == "" or int(hd) == 511 else int(hd),
                        ascii_name(r["vessel_name"]), num(r["vessel_type"], 0), num(r["length"], 0),
                        str(clean(r["transceiver"])).strip()]))
    out.sort(key=lambda x: (x[0], x[1][0]))
    with open(args.out, "w", encoding="ascii", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["mmsi", "t", "lat", "lon", "sog_kn", "cog", "heading", "name", "type", "length", "cls"])
        for _, row in out:
            wr.writerow(row)
    print("rows %d vessels %d" % (len(out), len({r[1][0] for r in out})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
