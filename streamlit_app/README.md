# GPU Price Tracker — Streamlit Dashboard

Public-facing visualization for the cross-cloud GPU pricing data this repo
collects. Reads partitioned Parquet files from a private S3 bucket via
DuckDB's `httpfs` extension — the app **never downloads the full dataset**;
each query pulls only the bytes (and only the partitions) it needs. Three
views: latest prices, price trends per GPU family, and spot-vs-on-demand
spread.

## Architecture

```
S3 layout:
  s3://hubbard-gpu-price-data/
    prices/
      dt=2026-05-07/
        snapshot_20260507T091700Z.parquet
        snapshot_20260507T213000Z.parquet
      dt=2026-05-08/
        ...
```

CI writes one Parquet file per snapshot, never overwriting. DuckDB sees the
union via `read_parquet('s3://.../prices/**/*.parquet', hive_partitioning=true)`
and prunes by the `dt=` partition for every query.

## Local development

```bash
pip install -r streamlit_app/requirements.txt

# Convert SQLite -> local Parquet tree (one-time, for dev)
python3 scripts/sqlite_to_parquet.py \
    --db data/gpu_prices.db \
    --out data/parquet

# Run the app pointed at the local tree
LOCAL_PARQUET=1 streamlit run streamlit_app/app.py

# Or against S3 with real credentials
cp streamlit_app/.streamlit/secrets.toml.example \
   streamlit_app/.streamlit/secrets.toml
# fill in keys, then:
streamlit run streamlit_app/app.py
```

`streamlit_app/.streamlit/secrets.toml` is gitignored — never commit it.

## Bootstrap S3 from existing SQLite (one-time)

```bash
python3 scripts/sqlite_to_parquet.py --db data/gpu_prices.db --out data/parquet
aws s3 sync data/parquet/prices/ s3://hubbard-gpu-price-data/prices/ --size-only
```

`--size-only` makes re-runs incremental — only new snapshot files are
uploaded.

## Deploy to Streamlit Community Cloud

1. **Create a read-only IAM user** in AWS console:
   - User name: `gpu-price-streamlit-reader`
   - Inline policy (allows listing the prefix and reading any object under it):
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": "s3:ListBucket",
           "Resource": "arn:aws:s3:::hubbard-gpu-price-data",
           "Condition": {
             "StringLike": {"s3:prefix": ["prices/*", "prices"]}
           }
         },
         {
           "Effect": "Allow",
           "Action": "s3:GetObject",
           "Resource": "arn:aws:s3:::hubbard-gpu-price-data/prices/*"
         }
       ]
     }
     ```
   - Create an access key for the user and save it.

2. **Create the app** at https://share.streamlit.io:
   - Repository: `alex-hubbard/gpu_price_tracker`
   - Branch: `main`
   - Main file path: `streamlit_app/app.py`
   - Python version: 3.11

3. **Paste secrets** into *Settings → Secrets* (TOML):
   ```toml
   [aws]
   access_key_id = "AKIA..."
   secret_access_key = "..."
   bucket = "hubbard-gpu-price-data"
   prefix = "prices"
   region = "us-east-1"
   ```

4. Deploy. New snapshots show up at most ~1 hour after CI uploads them
   (Streamlit's `@st.cache_data(ttl=3600)`).

## How it works

- `queries.py` opens one DuckDB connection per session. With
  `LOCAL_PARQUET=1` it reads `data/parquet/prices/**/*.parquet`; otherwise
  it `INSTALL`s `httpfs`, configures S3 creds from `st.secrets["aws"]`, and
  reads `s3://<bucket>/<prefix>/**/*.parquet`.
- All queries hit a single `prices` view; partition pruning by `dt` keeps
  cold-start latency low even as the dataset grows.
- `app.py` is one page with a KPI header, sidebar filters (GPU, provider,
  spot/on-demand, lookback), and three tabs.
- Schema reference: `../database.py` (column meanings) and
  `../MODELING_GPU_USAGE_TRENDS.md` (analytical context).
