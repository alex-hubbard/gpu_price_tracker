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
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import regions  # noqa: E402  — sibling module at repo root


def _git_sha() -> str:
    """Return the current commit SHA, or empty string if unavailable."""
    if not shutil.which("git"):
        return ""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _gpuhunt_version() -> str:
    """Return the installed gpuhunt version, or empty string if missing."""
    try:
        import importlib.metadata as md
        return md.version("gpuhunt")
    except Exception:
        return ""


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
    "quality",
)


def _existing_columns(conn: sqlite3.Connection) -> set:
    """Names of columns that actually exist in gpu_prices today."""
    return {row[1] for row in conn.execute("PRAGMA table_info(gpu_prices)")}


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

    # Source schema may pre-date the `quality` migration (older SQLite DBs).
    # Select only what the table actually has, then synthesize defaults.
    have = _existing_columns(conn)
    cols_to_select = [c for c in SNAPSHOT_COLUMNS if c in have]
    df = pd.read_sql_query(
        f"SELECT {', '.join(cols_to_select)} FROM gpu_prices WHERE timestamp = ?",
        conn,
        params=[ts_str],
    )
    if "quality" not in df.columns:
        # Source SQLite predates the migration — synthesize quality tags so
        # the published Parquet still carries accurate flags for CPU-only
        # and Unknown-GPU rows.
        df["quality"] = [
            "cpu_only" if (c is None or c <= 0)
            else "unknown_gpu" if g == "Unknown"
            else "missing_memory" if (m is None or pd.isna(m))
            else "ok"
            for c, g, m in zip(df["gpu_count"], df["gpu_type"], df["gpu_memory_gb"])
        ]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["is_spot"] = df["is_spot"].astype(bool)
    df["available"] = df["available"].astype("boolean")  # nullable
    df = regions.enrich(df)  # adds region_canonical/country/region_*/region_group
    pdir.mkdir(parents=True, exist_ok=True)

    # Embed provenance in Parquet file metadata. Keys/values must be bytes
    # for pyarrow; we keep the surface small and self-describing.
    quality_summary = (
        df["quality"].value_counts().to_dict() if "quality" in df.columns else {}
    )
    file_metadata = {
        b"snapshot_timestamp": str(ts).encode(),
        b"snapshot_timestamp_utc": ts.astimezone(timezone.utc).isoformat().encode()
            if ts.tzinfo
            else ts.isoformat().encode(),
        b"emitted_at_utc": datetime.now(timezone.utc).isoformat().encode(),
        b"git_sha": _git_sha().encode(),
        b"gpuhunt_version": _gpuhunt_version().encode(),
        b"row_count": str(len(df)).encode(),
        b"quality_summary": ",".join(
            f"{k}={v}" for k, v in sorted(quality_summary.items())
        ).encode(),
        b"schema_version": b"1.1",
    }
    table = pa.Table.from_pandas(df, preserve_index=False)
    # Merge our keys into any existing pandas metadata so downstream
    # readers (e.g. pandas.read_parquet) keep their type roundtrip info.
    existing = table.schema.metadata or {}
    table = table.replace_schema_metadata({**existing, **file_metadata})
    pq.write_table(table, pfile, compression="zstd")
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
