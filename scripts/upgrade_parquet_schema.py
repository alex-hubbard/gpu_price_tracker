#!/usr/bin/env python3
"""Upgrade pre-v1.1 Parquet snapshots in place to the current schema.

Snapshot files written before schema v1.1 carry 13 columns. v1.1 (emitted by
`sqlite_to_parquet.py` since 2026-07) adds:

- `quality`          — row-quality tag ('ok' | 'cpu_only' | 'unknown_gpu' |
                       'missing_memory'), synthesized here from the row itself
- `region_canonical`, `country`, `region_lat`, `region_lon`, `region_group`
                     — canonical region enrichment via `regions.enrich()`
- file-level metadata (schema_version, row_count, quality_summary, ...)

This script rewrites only files that are not already v1.1, casting them to the
exact Arrow schema of a reference v1.1 file so the published tree stays
byte-schema uniform (readers do not need `union_by_name`). Rewrites are
atomic (tmp file + rename). Idempotent: a second run is a no-op.

Usage:
    python3 scripts/upgrade_parquet_schema.py --root data/parquet/prices [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import regions  # noqa: E402  — sibling module at repo root

SCHEMA_VERSION = b"1.1"
REGION_COLUMNS = ("region_canonical", "country", "region_lat", "region_lon", "region_group")


def synthesize_quality(df: pd.DataFrame) -> pd.Series:
    """Same tagging rules as sqlite_to_parquet.py's pre-migration fallback."""
    def tag(row) -> str:
        if row.gpu_count is None or pd.isna(row.gpu_count) or row.gpu_count <= 0:
            return "cpu_only"
        if row.gpu_type == "Unknown":
            return "unknown_gpu"
        if row.gpu_memory_gb is None or pd.isna(row.gpu_memory_gb):
            return "missing_memory"
        return "ok"

    return df.apply(tag, axis=1)


def find_reference_schema(files: list[Path]) -> pa.Schema | None:
    """Arrow schema of any file already at v1.1, to cast upgraded files to."""
    for f in files:
        schema = pq.read_schema(f)
        md = schema.metadata or {}
        if md.get(b"schema_version") == SCHEMA_VERSION and "quality" in schema.names:
            return schema
    return None


def upgrade_file(path: Path, ref_schema: pa.Schema, dry_run: bool) -> bool:
    schema = pq.read_schema(path)
    if (schema.metadata or {}).get(b"schema_version") == SCHEMA_VERSION:
        return False

    if dry_run:
        print(f"would upgrade: {path}")
        return True

    df = pq.read_table(path).to_pandas()
    if "quality" not in df.columns:
        df["quality"] = synthesize_quality(df)
    if any(c not in df.columns for c in REGION_COLUMNS):
        df = df.drop(columns=[c for c in REGION_COLUMNS if c in df.columns])
        df = regions.enrich(df)

    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.select(ref_schema.names).cast(ref_schema.remove_metadata())

    quality_summary = df["quality"].value_counts().to_dict()
    snapshot_ts = pd.Timestamp(table["timestamp"][0].as_py())
    metadata = {
        b"snapshot_timestamp_utc": snapshot_ts.isoformat().encode(),
        b"emitted_at_utc": datetime.now(timezone.utc).isoformat().encode(),
        b"row_count": str(len(df)).encode(),
        b"quality_summary": ",".join(
            f"{k}={v}" for k, v in sorted(quality_summary.items())
        ).encode(),
        b"schema_version": SCHEMA_VERSION,
        b"backfilled": b"true",  # upgraded from a pre-v1.1 file, not re-collected
    }
    existing = table.schema.metadata or {}
    table = table.replace_schema_metadata({**existing, **metadata})

    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)
    print(f"upgraded: {path}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="data/parquet/prices")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(Path(args.root).glob("dt=*/*.parquet"))
    if not files:
        print(f"ERROR: no snapshot files under {args.root}", file=sys.stderr)
        sys.exit(2)

    ref = find_reference_schema(files)
    if ref is None:
        print("ERROR: no v1.1 reference file found; emit one first "
              "(scripts/emit_latest_parquet.py).", file=sys.stderr)
        sys.exit(2)

    changed = sum(upgrade_file(f, ref, args.dry_run) for f in files)
    print(f"{changed}/{len(files)} files {'need upgrading' if args.dry_run else 'upgraded'}.")


if __name__ == "__main__":
    main()
