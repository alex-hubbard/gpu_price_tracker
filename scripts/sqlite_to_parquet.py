#!/usr/bin/env python3
"""Convert a SQLite gpu_prices.db into a partitioned Parquet dataset.

Layout (Hive partitioning):
    <out>/prices/dt=YYYY-MM-DD/snapshot_<UTC ISO>.parquet

One Parquet file per distinct `timestamp` value in the source `gpu_prices`
table. Re-runs are idempotent: existing files are skipped.

Usage:
    python3 scripts/sqlite_to_parquet.py --db data/gpu_prices.db --out data/parquet
    python3 scripts/sqlite_to_parquet.py --db ... --out ... --limit-snapshots 5
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


SNAPSHOT_COLUMNS = (
    "timestamp",
    "provider",
    "instance_type",
    "gpu_type",
    "gpu_count",
    "gpu_memory_gb",
    "vcpus",
    "ram_gb",
    "region",
    "price_per_hour",
    "is_spot",
    "available",
    "availability_zone",
)


def snapshot_filename(ts: datetime) -> str:
    return f"snapshot_{ts.strftime('%Y%m%dT%H%M%SZ')}.parquet"


def partition_dir(out: Path, ts: datetime) -> Path:
    return out / "prices" / f"dt={ts.strftime('%Y-%m-%d')}"


def write_snapshot(conn: sqlite3.Connection, ts_str: str, out: Path) -> bool:
    """Write one snapshot file. Returns True if written, False if skipped."""
    ts = datetime.fromisoformat(ts_str)
    pdir = partition_dir(out, ts)
    pfile = pdir / snapshot_filename(ts)
    if pfile.exists():
        return False

    cols = ", ".join(SNAPSHOT_COLUMNS)
    df = pd.read_sql_query(
        f"SELECT {cols} FROM gpu_prices WHERE timestamp = ?",
        conn,
        params=[ts_str],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["is_spot"] = df["is_spot"].astype(bool)
    df["available"] = df["available"].astype("boolean")  # nullable
    pdir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        pfile,
        compression="zstd",
    )
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="Path to source SQLite DB")
    ap.add_argument("--out", required=True, help="Output directory root")
    ap.add_argument(
        "--limit-snapshots",
        type=int,
        default=None,
        help="Convert only the N most recent snapshots (debugging)",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    timestamps = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT timestamp FROM gpu_prices ORDER BY timestamp DESC"
        )
    ]
    if args.limit_snapshots:
        timestamps = timestamps[: args.limit_snapshots]
    print(f"{len(timestamps)} snapshots to convert -> {out}")

    written = skipped = 0
    for i, ts_str in enumerate(timestamps, 1):
        if write_snapshot(conn, ts_str, out):
            written += 1
        else:
            skipped += 1
        if i % 10 == 0 or i == len(timestamps):
            print(f"  [{i}/{len(timestamps)}] written={written} skipped={skipped}")

    print(f"Done. written={written} skipped={skipped}")


if __name__ == "__main__":
    main()
