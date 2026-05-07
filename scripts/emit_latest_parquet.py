#!/usr/bin/env python3
"""Emit the most recent SQLite snapshot as a single Parquet file.

Used after `collect.py` to publish the day's snapshot. The resulting file is
placed under `<out>/prices/dt=YYYY-MM-DD/snapshot_<UTC ISO>.parquet` so a
subsequent `aws s3 sync` propagates only the new file to S3.

Idempotent: if a Parquet file for the latest timestamp already exists, the
script is a no-op and exits 0.

Usage:
    python3 scripts/emit_latest_parquet.py --db data/gpu_prices.db --out data/parquet
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlite_to_parquet import write_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    row = conn.execute("SELECT MAX(timestamp) FROM gpu_prices").fetchone()
    latest = row[0] if row else None
    if not latest:
        print("ERROR: SQLite DB has no rows; nothing to emit.", file=sys.stderr)
        sys.exit(2)

    written = write_snapshot(conn, latest, out)
    if written:
        print(f"Wrote Parquet for snapshot {latest}")
    else:
        print(f"Snapshot {latest} already present; nothing to do.")


if __name__ == "__main__":
    main()
