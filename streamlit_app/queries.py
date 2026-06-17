"""DuckDB query helpers — reads partitioned Parquet from S3 (or a local dir).

The app never downloads the full dataset. DuckDB's httpfs extension issues
range requests to S3 and prunes by the `dt=YYYY-MM-DD` partition column, so
trend / spread / latest-snapshot queries each touch only the files they need.

A `regions` view (loaded from `data/regions.csv`) is also registered, and
all listing-level queries LEFT JOIN it to expose `region_canonical`,
`country`, and `region_group` for cross-cloud regional analysis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import streamlit as st

# Repo root on sys.path so we can import the sibling `regions` module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import regions as regions_module  # noqa: E402


def _aws_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    if "aws" in st.secrets and key in st.secrets["aws"]:
        return st.secrets["aws"][key]
    return default


@st.cache_resource
def get_con() -> duckdb.DuckDBPyConnection:
    """One DuckDB connection per Streamlit session, configured for S3 or local."""
    con = duckdb.connect(":memory:")

    if os.environ.get("LOCAL_PARQUET"):
        # Dev mode: read from a local parquet partition tree.
        root = os.environ.get("LOCAL_PARQUET_PATH", "data/parquet")
        glob = f"{root}/prices/**/*.parquet"
    else:
        con.execute("INSTALL httpfs; LOAD httpfs;")
        bucket = _aws_secret("bucket", "hubbard-gpu-price-data")
        prefix = _aws_secret("prefix", "prices")
        region = _aws_secret("region", "us-east-1")
        access_key = _aws_secret("access_key_id")
        secret_key = _aws_secret("secret_access_key")
        # DuckDB SET requires literals — these come from Streamlit secrets,
        # not user input, so string interpolation is safe.
        con.execute(f"SET s3_region='{region}'")
        if access_key and secret_key:
            con.execute(f"SET s3_access_key_id='{access_key}'")
            con.execute(f"SET s3_secret_access_key='{secret_key}'")
        else:
            # Anonymous read mode: requires the S3 bucket policy to grant
            # public s3:GetObject + s3:ListBucket on the prices/ prefix.
            con.execute("SET s3_use_ssl=true")
            con.execute("SET s3_url_style='vhost'")
        glob = f"s3://{bucket}/{prefix}/**/*.parquet"

    con.execute(
        f"""
        CREATE OR REPLACE VIEW prices_raw AS
        SELECT *
        FROM read_parquet('{glob}', hive_partitioning = true)
        """
    )

    # Register the regions lookup as a DuckDB table so we can JOIN in SQL.
    regions_df = regions_module.load_regions().rename(
        columns={"lat": "region_lat", "lon": "region_lon"}
    )
    con.register("regions_df", regions_df)
    con.execute(
        """
        CREATE OR REPLACE VIEW regions AS
        SELECT provider, raw_region AS region,
               region_canonical, country,
               CAST(region_lat AS DOUBLE) AS region_lat,
               CAST(region_lon AS DOUBLE) AS region_lon,
               region_group
        FROM regions_df
        """
    )

    # Build the canonical `prices` view. We always expose `quality`,
    # `region_canonical`, `country`, `region_lat`, `region_lon`, and
    # `region_group` so downstream queries don't have to think about which
    # snapshot vintage the data came from.
    sample_columns = {
        c[0]
        for c in con.execute("DESCRIBE prices_raw").fetchall()
    }
    select_parts = ["p.*"]
    if "region_canonical" not in sample_columns:
        select_parts += [
            "r.region_canonical AS region_canonical",
            "r.country AS country",
            "r.region_lat AS region_lat",
            "r.region_lon AS region_lon",
            "r.region_group AS region_group",
        ]
        join_clause = (
            "LEFT JOIN regions r "
            "ON p.provider = r.provider AND p.region = r.region"
        )
    else:
        join_clause = ""

    if "quality" not in sample_columns:
        # Synthesize a quality column for older snapshots so the same
        # `quality = 'ok'` filter works everywhere.
        select_parts.append(
            "CASE WHEN gpu_count <= 0 THEN 'cpu_only' "
            "     WHEN gpu_type = 'Unknown' THEN 'unknown_gpu' "
            "     ELSE 'ok' END AS quality"
        )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW prices AS
        SELECT {', '.join(select_parts)}
        FROM prices_raw p
        {join_clause}
        """
    )
    return con


@st.cache_data(ttl=3600)
def load_stats() -> dict:
    con = get_con()
    row = con.execute(
        """
        SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT timestamp),
               COUNT(*), COUNT(DISTINCT provider), COUNT(DISTINCT gpu_type)
        FROM prices
        """
    ).fetchone()
    return {
        "first_snapshot": str(row[0]) if row[0] else None,
        "last_snapshot": str(row[1]) if row[1] else None,
        "snapshots": row[2],
        "total_records": row[3],
        "providers": row[4],
        "gpu_types": row[5],
    }


@st.cache_data(ttl=3600)
def load_latest_snapshot() -> pd.DataFrame:
    """Latest snapshot (one row per listing) with derived price_per_gpu_hour.

    Excludes gpu_count = 0 (CPU-only artifacts) and Unknown gpu_type.
    """
    con = get_con()
    df = con.execute(
        """
        SELECT timestamp, provider, instance_type, gpu_type, gpu_count,
               gpu_memory_gb, vcpus, ram_gb, region,
               region_canonical, country, region_group,
               price_per_hour,
               is_spot, available, availability_zone
        FROM prices
        WHERE timestamp = (SELECT MAX(timestamp) FROM prices)
          AND quality = 'ok'
        """
    ).df()
    df["is_spot"] = df["is_spot"].astype(bool)
    df["price_per_gpu_hour"] = df["price_per_hour"] / df["gpu_count"]
    return df


@st.cache_data(ttl=3600)
def load_provider_freshness() -> pd.DataFrame:
    """Per-provider last-seen timestamp and listing count.

    Returns one row per provider sorted by `last_seen` descending. Used to
    render the freshness panel in the app header — providers that have not
    appeared in a recent snapshot indicate a scraper outage.
    """
    con = get_con()
    df = con.execute(
        """
        WITH per_provider AS (
            SELECT provider,
                   MAX(timestamp) AS last_seen
            FROM prices
            WHERE quality = 'ok'
            GROUP BY provider
        ),
        latest_listings AS (
            SELECT provider, COUNT(*) AS listings_in_latest
            FROM prices
            WHERE timestamp = (SELECT MAX(timestamp) FROM prices)
              AND quality = 'ok'
            GROUP BY provider
        )
        SELECT p.provider,
               p.last_seen,
               COALESCE(l.listings_in_latest, 0) AS listings_in_latest
        FROM per_provider p
        LEFT JOIN latest_listings l USING (provider)
        ORDER BY p.last_seen DESC, p.provider
        """
    ).df()
    if not df.empty:
        df["last_seen"] = pd.to_datetime(df["last_seen"])
    return df


@st.cache_data(ttl=3600)
def load_filter_options() -> dict:
    con = get_con()
    gpu_types = con.execute(
        """
        SELECT gpu_type FROM prices
        WHERE quality = 'ok'
        GROUP BY gpu_type ORDER BY COUNT(*) DESC
        """
    ).df()["gpu_type"].tolist()
    providers = con.execute(
        """
        SELECT provider FROM prices
        WHERE quality = 'ok'
        GROUP BY provider ORDER BY COUNT(*) DESC
        """
    ).df()["provider"].tolist()
    region_groups = con.execute(
        """
        SELECT region_group FROM prices
        WHERE region_group IS NOT NULL
          AND quality = 'ok'
        GROUP BY region_group ORDER BY COUNT(*) DESC
        """
    ).df()["region_group"].tolist()
    return {
        "gpu_types": gpu_types,
        "providers": providers,
        "region_groups": region_groups,
    }


def _quoted_in_clause(values: tuple[str, ...]) -> str:
    """Build a SQL IN-list from a small set of trusted strings."""
    safe = [v.replace("'", "''") for v in values]
    return ", ".join(f"'{v}'" for v in safe)


@st.cache_data(ttl=3600)
def load_trends(
    gpu_types: tuple[str, ...] = (),
    providers: tuple[str, ...] = (),
    region_groups: tuple[str, ...] = (),
    is_spot: Optional[bool] = None,
    days: int = 30,
) -> pd.DataFrame:
    """Daily-aggregated $/GPU-hr per gpu_type within the lookback window."""
    where = [
        "timestamp >= (SELECT MAX(timestamp) FROM prices) - INTERVAL '{} days'".format(int(days)),
        "quality = 'ok'",
    ]
    if gpu_types:
        where.append(f"gpu_type IN ({_quoted_in_clause(gpu_types)})")
    if providers:
        where.append(f"provider IN ({_quoted_in_clause(providers)})")
    if region_groups:
        where.append(f"region_group IN ({_quoted_in_clause(region_groups)})")
    if is_spot is not None:
        where.append(f"is_spot = {str(bool(is_spot)).upper()}")

    sql = f"""
        SELECT CAST(timestamp AS DATE) AS day,
               gpu_type,
               AVG(price_per_hour / gpu_count) AS avg_price_per_gpu_hour,
               MIN(price_per_hour / gpu_count) AS min_price_per_gpu_hour,
               MAX(price_per_hour / gpu_count) AS max_price_per_gpu_hour,
               COUNT(*) AS listings
        FROM prices
        WHERE {' AND '.join(where)}
        GROUP BY day, gpu_type
        ORDER BY day, gpu_type
    """
    df = get_con().execute(sql).df()
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


@st.cache_data(ttl=3600)
def load_regional_dispersion(
    gpu_type: str,
    provider: str,
    days: int = 30,
) -> pd.DataFrame:
    """Daily $/GPU-hr by canonical region for a fixed (gpu_type, provider).

    Powers the Regional dispersion tab — implements MODELING §3.4
    (regional demand concentration / arbitrage). Returns one row per
    (day, region_canonical) with avg/min/max price-per-GPU-hour and
    a listing count; downstream code can compute coefficient of
    variation across regions per day from this.
    """
    safe_gpu = gpu_type.replace("'", "''")
    safe_prov = provider.replace("'", "''")
    sql = f"""
        WITH t AS (
            SELECT CAST(timestamp AS DATE) AS day,
                   COALESCE(region_canonical, region) AS region,
                   region_group,
                   price_per_hour / gpu_count AS p
            FROM prices
            WHERE gpu_type = '{safe_gpu}'
              AND provider = '{safe_prov}'
              AND quality = 'ok'
              AND timestamp >= (SELECT MAX(timestamp) FROM prices) - INTERVAL '{int(days)} days'
        )
        SELECT day,
               region,
               region_group,
               AVG(p) AS avg_price_per_gpu_hour,
               MIN(p) AS min_price_per_gpu_hour,
               MAX(p) AS max_price_per_gpu_hour,
               COUNT(*) AS listings
        FROM t
        GROUP BY day, region, region_group
        ORDER BY day, region
    """
    df = get_con().execute(sql).df()
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


@st.cache_data(ttl=3600)
def load_spread(gpu_type: str, days: int = 30) -> pd.DataFrame:
    """Daily on-demand minus spot $/GPU-hr per provider, for one GPU family."""
    safe_gpu = gpu_type.replace("'", "''")
    sql = f"""
        SELECT CAST(s.timestamp AS DATE) AS day,
               s.provider,
               AVG(s.price_per_hour / s.gpu_count) AS spot_price,
               AVG(od.price_per_hour / od.gpu_count) AS on_demand_price,
               AVG((od.price_per_hour - s.price_per_hour) / s.gpu_count) AS spread,
               COUNT(*) AS pairs
        FROM prices s
        JOIN prices od
          ON s.timestamp = od.timestamp
         AND s.provider = od.provider
         AND s.instance_type = od.instance_type
         AND s.region = od.region
         AND s.is_spot = TRUE AND od.is_spot = FALSE
        WHERE s.gpu_type = '{safe_gpu}'
          AND s.quality = 'ok'
          AND s.timestamp >= (SELECT MAX(timestamp) FROM prices) - INTERVAL '{int(days)} days'
        GROUP BY day, s.provider
        ORDER BY day, s.provider
    """
    df = get_con().execute(sql).df()
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df
