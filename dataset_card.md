---
license: cc-by-4.0
task_categories:
  - tabular-regression
language:
  - en
tags:
  - gpu
  - cloud-computing
  - pricing
  - market-microstructure
  - h100
  - a100
pretty_name: GPU Price Tracker
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: prices/**/*.parquet
---

# GPU Price Tracker

A continuously-updated dataset of **cross-cloud GPU rental pricing**
covering 13 public cloud providers (AWS, GCP, Azure, Lambda Labs,
RunPod, Vast.ai, DataCrunch, Cudo Compute, TensorDock, Vultr, Oracle,
Nebius, CloudRift): 3M+ listing observations, 70+ GPU types, collected
twice daily since January 2026 by scraping provider pricing surfaces via
the [`gpuhunt`](https://github.com/dstackai/gpuhunt) library and
published as Hive-partitioned Parquet files
(`prices/dt=YYYY-MM-DD/*.parquet`).

The dataset is intended for:

- **Researchers** studying cloud-market microstructure, GPU price
  dynamics, and the spot–on-demand spread as a utilization proxy.
- **Practitioners** comparing GPU rental costs across providers for
  capacity planning, procurement, and ML-training cost estimation.

Explore it interactively at the hosted dashboard:
**<https://gpu-price-trends.streamlit.app/>**.

## Quick start

```python
from datasets import load_dataset

ds = load_dataset("afhubbard/gpu-prices", split="train")
print(ds[0])
# {'timestamp': '2026-05-07T09:17:00Z', 'provider': 'aws',
#  'instance_type': 'p4d.24xlarge', 'gpu_type': 'A100', 'gpu_count': 8,
#  'gpu_memory_gb': 40, 'vcpus': 96, 'ram_gb': 1152.0,
#  'region': 'us-east-1', 'price_per_hour': 32.7726, 'is_spot': False,
#  'available': True, 'availability_zone': None, 'quality': 'ok',
#  'region_canonical': 'us-east-virginia', 'country': 'US',
#  'region_lat': 38.13, 'region_lon': -78.45,
#  'region_group': 'North America East'}
```

Or with DuckDB directly (no `datasets` install required):

```python
import duckdb
con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs;")
con.sql("""
SELECT gpu_type,
       AVG(price_per_hour / gpu_count) AS avg_price_per_gpu_hour,
       COUNT(*) AS listings
FROM read_parquet('hf://datasets/afhubbard/gpu-prices/prices/**/*.parquet',
                  hive_partitioning = true)
WHERE timestamp = (SELECT MAX(timestamp) FROM read_parquet(
                       'hf://datasets/afhubbard/gpu-prices/prices/**/*.parquet',
                       hive_partitioning = true))
  AND quality = 'ok'
GROUP BY gpu_type
ORDER BY avg_price_per_gpu_hour
LIMIT 10
""").show()
```

## Schema

| Column | Type | Description |
| --- | --- | --- |
| `timestamp` | timestamp (UTC) | When the snapshot was taken |
| `provider` | string | Cloud provider id |
| `instance_type` | string | Provider SKU |
| `gpu_type` | string | Normalized accelerator family (`H100`, `A100`, …) |
| `gpu_count` | int32 | GPUs per SKU |
| `gpu_memory_gb` | int32 (nullable) | VRAM per GPU |
| `vcpus` | int32 | Host vCPUs |
| `ram_gb` | float32 | Host RAM in GB |
| `region` | string | Provider's raw region (not canonicalized) |
| `price_per_hour` | float32 | USD/hr for the full SKU |
| `is_spot` | bool | Spot/preemptible flag (semantics vary; see methodology) |
| `available` | bool (nullable) | Listed and offerable at scrape time |
| `availability_zone` | string (nullable) | Zone within the region, where applicable |
| `quality` | string | `ok`, `cpu_only`, `unknown_gpu`, or `missing_memory` — filter to `'ok'` for most analyses |
| `region_canonical` | string (nullable) | Canonicalized region name (cross-cloud comparable) |
| `country` | string (nullable) | ISO country code of the region |
| `region_lat`, `region_lon` | double (nullable) | Approximate region coordinates |
| `region_group` | string (nullable) | Coarse geographic bucket (e.g. `North America East`) |

Compute `price_per_gpu_hour = price_per_hour / gpu_count` for fair
cross-SKU comparison.

The `quality` and region columns were added in schema v1.1 (July 2026);
all earlier snapshot files were upgraded in place, so every file in the
tree has the same schema. Each Parquet file also embeds provenance
metadata (`schema_version`, `row_count`, `quality_summary`, and
`backfilled = true` on upgraded files).

## Collection cadence

Twice daily (~09:00 and 21:00 UTC) via a GitHub Actions cron. Files
are append-only — each run produces a new immutable Parquet file under
`prices/dt=<UTC date>/`.

## Limitations (read before modeling)

- **Region canonicalization is best-effort** — `region_canonical` and
  friends come from a hand-maintained lookup and are NULL for raw
  regions not yet mapped; fall back with
  `COALESCE(region_canonical, region)`.
- **Spot semantics differ** by provider (AWS auction vs. Vast.ai P2P,
  etc.). See the methodology document.
- **No customer telemetry** — the data is supply/listing prices only.
- **Noisy rows are tagged, not dropped** — historical snapshots contain
  `cpu_only` and `unknown_gpu` rows. Filter to `quality = 'ok'` for
  most analyses.
- **12-hour cadence** — too coarse for intraday auction analyses.

Full methodology, provider-by-provider notes, and a list of analytical
questions the data does and does not support:
[methodology.md](https://github.com/alex-hubbard/gpu_price_tracker/blob/main/methodology.md)
and
[MODELING_GPU_USAGE_TRENDS.md](https://github.com/alex-hubbard/gpu_price_tracker/blob/main/MODELING_GPU_USAGE_TRENDS.md).

## License

CC BY 4.0. Suggested citation:

```bibtex
@misc{hubbard2026gpuprices,
  author       = {Alex Hubbard},
  title        = {GPU Price Tracker},
  year         = {2026},
  howpublished = {\url{https://github.com/alex-hubbard/gpu_price_tracker}},
  note         = {Dataset and software, MIT (code) / CC BY 4.0 (data)}
}
```

## Source code

Collection pipeline, dashboard, and migration scripts live at
<https://github.com/alex-hubbard/gpu_price_tracker>.
