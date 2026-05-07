"""S3 fetch and cached SQL helpers for the Streamlit app."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Optional

import boto3
import pandas as pd
import streamlit as st


def _aws_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    if "aws" in st.secrets and key in st.secrets["aws"]:
        return st.secrets["aws"][key]
    return default


@st.cache_resource(ttl=3600)
def get_db_path() -> str:
    """Return a local path to the SQLite DB.

    If LOCAL_DB is set, use the repo's checked-in copy (dev escape hatch).
    Otherwise download s3://<bucket>/<key> using credentials from st.secrets["aws"].
    Cached for one hour so the app doesn't hit S3 on every rerun.
    """
    if os.environ.get("LOCAL_DB"):
        local = os.environ.get("LOCAL_DB_PATH", "data/gpu_prices.db")
        if not os.path.exists(local):
            raise FileNotFoundError(f"LOCAL_DB set but {local} not found")
        return local

    bucket = _aws_secret("bucket", "hubbard-gpu-price-data")
    key = _aws_secret("key", "gpu_prices.db")
    region = _aws_secret("region", "us-east-1")

    client = boto3.client(
        "s3",
        aws_access_key_id=_aws_secret("access_key_id"),
        aws_secret_access_key=_aws_secret("secret_access_key"),
        region_name=region,
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    client.download_file(bucket, key, tmp.name)
    return tmp.name


def _conn() -> sqlite3.Connection:
    path = get_db_path()
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@st.cache_data(ttl=3600)
def load_stats() -> dict:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT MIN(timestamp), MAX(timestamp),
                   COUNT(DISTINCT timestamp), COUNT(*),
                   COUNT(DISTINCT provider), COUNT(DISTINCT gpu_type)
            FROM gpu_prices
            """
        ).fetchone()
    return {
        "first_snapshot": row[0],
        "last_snapshot": row[1],
        "snapshots": row[2],
        "total_records": row[3],
        "providers": row[4],
        "gpu_types": row[5],
    }


@st.cache_data(ttl=3600)
def load_latest_snapshot() -> pd.DataFrame:
    """Latest snapshot as a DataFrame with derived price_per_gpu_hour.

    Excludes rows with gpu_count = 0 (CPU-only artifacts that slip through
    the upstream scraper) and Unknown gpu_type (unmapped SKUs).
    """
    with _conn() as conn:
        df = pd.read_sql_query(
            """
            SELECT timestamp, provider, instance_type, gpu_type, gpu_count,
                   gpu_memory_gb, vcpus, ram_gb, region, price_per_hour,
                   is_spot, available, availability_zone
            FROM gpu_prices
            WHERE timestamp = (SELECT MAX(timestamp) FROM gpu_prices)
              AND gpu_count > 0
              AND gpu_type != 'Unknown'
            """,
            conn,
        )
    df["is_spot"] = df["is_spot"].astype(bool)
    df["price_per_gpu_hour"] = df["price_per_hour"] / df["gpu_count"]
    return df


@st.cache_data(ttl=3600)
def load_filter_options() -> dict:
    """Distinct values for sidebar filters, ordered by frequency.

    Drops Unknown gpu_type and CPU-only (gpu_count=0) rows so the filter
    dropdowns don't lead with noise.
    """
    with _conn() as conn:
        gpu_types = pd.read_sql_query(
            "SELECT gpu_type, COUNT(*) AS n FROM gpu_prices "
            "WHERE gpu_count > 0 AND gpu_type != 'Unknown' "
            "GROUP BY gpu_type ORDER BY n DESC",
            conn,
        )["gpu_type"].tolist()
        providers = pd.read_sql_query(
            "SELECT provider, COUNT(*) AS n FROM gpu_prices "
            "WHERE gpu_count > 0 AND gpu_type != 'Unknown' "
            "GROUP BY provider ORDER BY n DESC",
            conn,
        )["provider"].tolist()
    return {"gpu_types": gpu_types, "providers": providers}


@st.cache_data(ttl=3600)
def load_trends(
    gpu_types: tuple[str, ...] = (),
    providers: tuple[str, ...] = (),
    is_spot: Optional[bool] = None,
    days: int = 30,
) -> pd.DataFrame:
    """Daily aggregated $/GPU-hr per gpu_type."""
    where = [
        "timestamp >= datetime((SELECT MAX(timestamp) FROM gpu_prices), ?)",
        "gpu_count > 0",
        "gpu_type != 'Unknown'",
    ]
    params: list = [f"-{days} days"]
    if gpu_types:
        where.append(f"gpu_type IN ({','.join('?' * len(gpu_types))})")
        params.extend(gpu_types)
    if providers:
        where.append(f"provider IN ({','.join('?' * len(providers))})")
        params.extend(providers)
    if is_spot is not None:
        where.append("is_spot = ?")
        params.append(1 if is_spot else 0)

    sql = f"""
        SELECT DATE(timestamp) AS day,
               gpu_type,
               AVG(price_per_hour * 1.0 / gpu_count) AS avg_price_per_gpu_hour,
               MIN(price_per_hour * 1.0 / gpu_count) AS min_price_per_gpu_hour,
               MAX(price_per_hour * 1.0 / gpu_count) AS max_price_per_gpu_hour,
               COUNT(*) AS listings
        FROM gpu_prices
        WHERE {' AND '.join(where)}
        GROUP BY day, gpu_type
        ORDER BY day, gpu_type
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


@st.cache_data(ttl=3600)
def load_spread(gpu_type: str, days: int = 30) -> pd.DataFrame:
    """Daily on-demand minus spot $/GPU-hr per provider for one GPU family.

    Joins spot and on-demand listings on (timestamp, provider, instance_type, region).
    """
    sql = """
        SELECT DATE(s.timestamp) AS day,
               s.provider,
               AVG(s.price_per_hour * 1.0 / s.gpu_count) AS spot_price,
               AVG(od.price_per_hour * 1.0 / od.gpu_count) AS on_demand_price,
               AVG(
                 (od.price_per_hour - s.price_per_hour) * 1.0 / s.gpu_count
               ) AS spread,
               COUNT(*) AS pairs
        FROM gpu_prices s
        JOIN gpu_prices od
          ON s.timestamp = od.timestamp
         AND s.provider = od.provider
         AND s.instance_type = od.instance_type
         AND s.region = od.region
         AND s.is_spot = 1 AND od.is_spot = 0
        WHERE s.gpu_type = ?
          AND s.gpu_count > 0
          AND s.timestamp >= datetime((SELECT MAX(timestamp) FROM gpu_prices), ?)
        GROUP BY day, s.provider
        ORDER BY day, s.provider
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=[gpu_type, f"-{days} days"])
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df
