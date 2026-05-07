# GPU Price Tracker — Streamlit Dashboard

Public-facing visualization for the cross-cloud GPU pricing data this repo
collects. Reads partitioned Parquet files from S3 via DuckDB's `httpfs`
extension — the app **never downloads the full dataset**; each query pulls
only the bytes (and only the partitions) it needs. Four tabs: latest
prices, price trends per GPU family, spot-vs-on-demand spread, and an
About / Methodology page that includes BibTeX citation and bulk-download
snippets.

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

## Public access (default)

The bucket prefix `prices/` is configured for **anonymous read** via a
public bucket policy (see `Bucket policy` below). With no `[aws]`
secret set, `queries.py` opens an unauthenticated DuckDB session and
reads `s3://hubbard-gpu-price-data/prices/`. This is how the deployed
Streamlit Cloud app is configured.

The same data is mirrored to **Hugging Face Datasets** at
[`afhubbard/gpu-prices`](https://huggingface.co/datasets/afhubbard/gpu-prices),
which is the recommended surface for notebooks and `datasets.load_dataset`
users.

## Local development

```bash
pip install -r streamlit_app/requirements.txt

# Convert SQLite -> local Parquet tree (one-time, for dev)
python3 scripts/sqlite_to_parquet.py \
    --db data/gpu_prices.db \
    --out data/parquet

# Run the app pointed at the local tree
LOCAL_PARQUET=1 streamlit run streamlit_app/app.py

# Or against the public S3 mirror with no credentials
streamlit run streamlit_app/app.py
```

To use credentialed S3 access (e.g. while the bucket is still private
during initial setup):

```bash
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

## Bootstrap Hugging Face Datasets (one-time)

```bash
export HF_TOKEN=<token-with-write-access-to-the-dataset-repo>
python3 scripts/sync_to_huggingface.py \
    --src data/parquet/prices \
    --bootstrap        # also uploads dataset_card.md as the HF README
```

After bootstrap, the daily GitHub Action keeps the HF mirror in sync
incrementally (no `--bootstrap` flag).

## Deploy to Streamlit Community Cloud (anonymous-S3 mode)

1. **Apply the public bucket policy** (see "Bucket policy" below). Once
   applied, anyone — including Streamlit Cloud — can read the data
   without credentials.

2. **Create the app** at https://share.streamlit.io:
   - Repository: `alex-hubbard/gpu_price_tracker`
   - Branch: `main`
   - Main file path: `streamlit_app/app.py`
   - Python version: 3.11

3. **Leave secrets blank** — no AWS keys are required. (If you skip the
   public bucket policy and want to use a private bucket instead, paste
   `[aws] access_key_id / secret_access_key / bucket / prefix / region`
   into *Settings → Secrets* and the app falls back to authenticated
   reads.)

4. Deploy. New snapshots show up at most ~1 hour after CI uploads them
   (`@st.cache_data(ttl=3600)`).

## Bucket policy (public read on `prices/` only)

Apply this in S3 console → Bucket → Permissions → Bucket policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicListPrices",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::hubbard-gpu-price-data",
      "Condition": {
        "StringLike": {"s3:prefix": ["prices", "prices/*"]}
      }
    },
    {
      "Sid": "PublicReadPrices",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::hubbard-gpu-price-data/prices/*"
    }
  ]
}
```

Other prefixes (e.g. the legacy `gpu_prices.db` object) stay private.
Block Public Access settings on the bucket must permit bucket policies
that grant public read; AWS surfaces a banner if they don't.

## GitHub Actions setup

The daily collection workflow needs three secrets configured in the
GitHub repo:

| Secret | Used for |
| --- | --- |
| `AWS_ROLE_ARN` | OIDC role assumed by the workflow; needs `s3:GetObject`, `s3:PutObject` on `arn:aws:s3:::hubbard-gpu-price-data/prices/*` |
| `HF_TOKEN` | Hugging Face token with write access to the dataset repo (optional — workflow skips HF sync if unset) |

## How it works

- `queries.py` opens one DuckDB connection per session. With
  `LOCAL_PARQUET=1` it reads `data/parquet/prices/**/*.parquet`. Otherwise
  it `INSTALL`s `httpfs` and reads `s3://<bucket>/<prefix>/**/*.parquet` —
  authenticated if `[aws]` Streamlit secrets are present, anonymous
  otherwise.
- All queries hit a single `prices` view; partition pruning by `dt` keeps
  cold-start latency low even as the dataset grows.
- `app.py` is one page with a KPI header, freshness banner, per-provider
  coverage panel, sidebar filters, and four tabs.
- Schema reference: `../methodology.md` (canonical) and
  `../MODELING_GPU_USAGE_TRENDS.md` (analytical context).
