"""Region normalization layer.

Loads `data/regions.csv` once and exposes:

- `load_regions()` — returns the lookup as a DataFrame (cached on disk path).
- `enrich(df)` — left-joins canonical fields onto a DataFrame keyed on
  `(provider, region)`. Adds columns: `region_canonical`, `country`,
  `region_lat`, `region_lon`, `region_group`. Missing rows in the lookup
  surface as NaN; downstream code should treat NaN `region_group` as
  "Unmapped".

Used by both the Streamlit app (`streamlit_app/queries.py`) and the
collector's Parquet emitter (`scripts/emit_latest_parquet.py`) so the
canonical fields land in every published file.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Optional

import pandas as pd


REGIONS_CSV = Path(__file__).resolve().parent / "data" / "regions.csv"

# Columns added to the input DataFrame by `enrich()`.
ENRICHED_COLUMNS = (
    "region_canonical",
    "country",
    "region_lat",
    "region_lon",
    "region_group",
)


@functools.lru_cache(maxsize=1)
def load_regions(path: Optional[Path | str] = None) -> pd.DataFrame:
    """Load `data/regions.csv` (or a custom path) into a DataFrame.

    Cached for the process lifetime — call `load_regions.cache_clear()`
    to force a re-read after editing the CSV.
    """
    p = Path(path) if path else REGIONS_CSV
    if not p.exists():
        # Empty frame with the expected columns so downstream `enrich`
        # produces all-NaN columns instead of crashing.
        return pd.DataFrame(
            columns=[
                "provider",
                "raw_region",
                "region_canonical",
                "country",
                "lat",
                "lon",
                "region_group",
            ]
        )
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""])
    # Numeric coords; everything else stays string.
    for col in ("lat", "lon"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def enrich(df: pd.DataFrame, region_col: str = "region") -> pd.DataFrame:
    """Add canonical region fields to `df` via left-join on (provider, region).

    The input must contain `provider` and `region_col` columns. The
    returned DataFrame has the same rows in the same order, plus the
    columns listed in `ENRICHED_COLUMNS`. Existing columns of the same
    name are overwritten.
    """
    if df.empty:
        for col in ENRICHED_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        return df

    regions = load_regions().rename(
        columns={
            "raw_region": region_col,
            "lat": "region_lat",
            "lon": "region_lon",
        }
    )[
        [
            "provider",
            region_col,
            "region_canonical",
            "country",
            "region_lat",
            "region_lon",
            "region_group",
        ]
    ]

    # Drop existing enriched columns so the merge is clean.
    drop_cols = [c for c in ENRICHED_COLUMNS if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    return df.merge(regions, on=["provider", region_col], how="left")
