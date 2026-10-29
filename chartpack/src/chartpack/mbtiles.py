"""Minimal MBTiles reader/writer. Tiles are addressed xyz and stored TMS (row flipped)."""

import gzip
import sqlite3
from pathlib import Path
from typing import Iterator

import mapbox_vector_tile

_SCHEMA = """
create table metadata (name text, value text);
create unique index metadata_name on metadata (name);
create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);
create unique index tile_index on tiles (zoom_level, tile_column, tile_row);
"""


class MBTiles:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @classmethod
    def create(cls, path: Path, *, fmt: str) -> "MBTiles":
        Path(path).unlink(missing_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA)
        m = cls(conn)
        m.set_metadata({"format": fmt})
        return m

    @classmethod
    def open(cls, path: Path) -> "MBTiles":
        if not Path(path).exists():
            raise FileNotFoundError(path)
        return cls(sqlite3.connect(path))

    def __enter__(self) -> "MBTiles":
        return self

    def __exit__(self, *exc) -> None:
        if exc[0] is None:
            self._conn.commit()
        self._conn.close()

    def put_tile(self, z: int, x: int, y: int, data: bytes) -> None:
        self._conn.execute(
            "insert or replace into tiles values (?, ?, ?, ?)", (z, x, 2**z - 1 - y, data)
        )

    def get_tile(self, z: int, x: int, y: int) -> bytes | None:
        row = self._conn.execute(
            "select tile_data from tiles where zoom_level=? and tile_column=? and tile_row=?",
            (z, x, 2**z - 1 - y),
        ).fetchone()
        return None if row is None else row[0]

    def tiles_at(self, z: int) -> Iterator[tuple[int, int, bytes]]:
        for x, row, data in self._conn.execute(
            "select tile_column, tile_row, tile_data from tiles where zoom_level=? order by 1, 2", (z,)
        ):
            yield x, 2**z - 1 - row, data

    def metadata(self) -> dict[str, str]:
        return dict(self._conn.execute("select name, value from metadata"))

    def set_metadata(self, items: dict[str, str]) -> None:
        self._conn.executemany("insert or replace into metadata values (?, ?)", list(items.items()))
        self._conn.commit()

    def delete_metadata(self, keys: list[str]) -> None:
        self._conn.executemany("delete from metadata where name=?", [(k,) for k in keys])
        self._conn.commit()


def decode_pbf(data: bytes) -> dict[str, list[dict]]:
    """Decode a (possibly gzipped) vector tile to {layer: [GeoJSON-like features]}.

    Coordinates are tile pixels with y growing downward, like the tile grid
    (y_coord_down=True), so lon/lat conversion needs no flip.
    """
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    decoded = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})
    return {name: layer["features"] for name, layer in decoded.items()}
