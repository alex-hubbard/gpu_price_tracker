# Methodology

This document is the canonical reference for the **GPU Price Tracker
dataset**: how it is collected, what each column means, what is and is
not normalized across providers, and the limits of what the data can
support. It is intended for two audiences:

- Researchers who want to cite, replicate, or build on the dataset.
- Practitioners who want to understand exactly what they are looking at
  before making procurement or capacity decisions.

For analytical use cases and starter SQL on top of the dataset, see
[MODELING_GPU_USAGE_TRENDS.md](MODELING_GPU_USAGE_TRENDS.md). For
operating the collection pipeline yourself, see [GUIDE.md](GUIDE.md).

## 1. What the dataset is

A **panel of GPU rental listings** observed across public cloud
providers, sampled at a roughly twice-daily cadence. Each row is a
single listing — a `(provider, instance_type, region, is_spot)` offer —
seen at one snapshot timestamp.

Source listings are gathered via the
[`gpuhunt`](https://github.com/dstackai/gpuhunt) library, which
maintains scrapers for the supported providers and normalizes the raw
provider responses into a uniform `RawCatalogItem` schema. We then map
those into our own schema (see §3) and persist one row per listing per
snapshot.

The dataset does **not** capture customer-side telemetry: no rented
hours, concurrency, or per-tenant utilization. It captures the
**market microstructure** — what providers are offering, at what price,
in what region, at scrape time.

## 2. Collection cadence

- **Frequency**: nominally twice daily, at approximately 09:00 and
  21:00 UTC, via a GitHub Actions cron (`.github/workflows/daily_update.yml`).
- **Locality**: the cron job runs on GitHub-hosted Ubuntu runners; all
  timestamps are stored in UTC.
- **Resolution**: ~12 hours. Intra-day spot dynamics on
  marketplace providers (Vast.ai, RunPod) are smoothed out at this
  cadence.
- **Outage handling**: if `collect.py` returns zero rows, the workflow
  exits non-zero and skips the upload step. Snapshots are append-only
  Parquet files with names containing the snapshot timestamp, so a
  failed run never overwrites prior data.

## 3. Schema

Each Parquet file in the `prices/` partition tree contains one row per
listing observed in that snapshot. Columns:

| Column | Type | Description |
| --- | --- | --- |
| `timestamp` | timestamp (UTC) | When the snapshot was taken |
| `provider` | string | Lowercased cloud provider id (see §5) |
| `instance_type` | string | Provider-specific SKU identifier |
| `gpu_type` | string | Normalized accelerator family (e.g. `H100`, `A100`, `RTX4090`) |
| `gpu_count` | int32 | Number of accelerators in the SKU |
| `gpu_memory_gb` | int32 (nullable) | VRAM per GPU, in GB |
| `vcpus` | int32 | Host vCPU count |
| `ram_gb` | float32 | Host system memory, in GB |
| `region` | string | Provider's raw region string (NOT canonicalized; see §6) |
| `price_per_hour` | float32 | USD per hour for the full SKU (all GPUs) |
| `is_spot` | bool | Spot / preemptible flag (semantics differ by provider; see §7) |
| `available` | bool (nullable) | Whether the listing was offered at scrape time |
| `availability_zone` | string (nullable) | Sub-region zone where applicable |

Derived columns (computed at query time, not stored):

- `price_per_gpu_hour = price_per_hour / gpu_count`. Use this for
  cross-SKU comparison, never `price_per_hour` directly, since SKUs
  bundle 1, 2, 4, or 8 accelerators.

The unique key per snapshot is
`(timestamp, provider, instance_type, region, is_spot)`.

## 4. Partitioning & file format

```
s3://hubbard-gpu-price-data/prices/
  dt=2026-05-07/
    snapshot_20260507T091700Z.parquet
    snapshot_20260507T213000Z.parquet
  dt=2026-05-08/
    snapshot_20260508T091700Z.parquet
  ...
```

- **Format**: Apache Parquet, zstd-compressed.
- **Partitioning**: Hive-style on `dt` (the UTC date of the snapshot).
  DuckDB and Polars can both prune by `dt` when reading.
- **One file per snapshot**: simplifies CI (each run writes a new
  immutable file), avoids any compaction step, and keeps cold-start I/O
  proportional to the time window the query touches, not to the full
  dataset size.

## 5. Provider coverage

Providers actually present in the dataset (as of the most recent
snapshot used to compile this document):

| Provider id | Vendor | Notes |
| --- | --- | --- |
| `aws` | Amazon Web Services | On-demand and spot |
| `gcp` | Google Cloud Platform | On-demand, spot, preemptible |
| `azure` | Microsoft Azure | On-demand, spot |
| `oci` | Oracle Cloud Infrastructure | On-demand |
| `lambdalabs` | Lambda Labs | On-demand |
| `runpod` | RunPod | Community + secure cloud |
| `vastai` | Vast.ai | Peer-to-peer marketplace |
| `datacrunch` | DataCrunch | On-demand |
| `cudo` | Cudo Compute | Decentralized marketplace |
| `nebius` | Nebius | On-demand |
| `cloudrift` | CloudRift | On-demand |
| `vultr` | Vultr | On-demand |
| `tensordock` | TensorDock | **Fragile**: the upstream API has changed shape repeatedly. Our collector wraps it in a guarded patch (`collect.py:16-117`); when the upstream returns an unexpected payload we silently emit zero rows for this provider. Coverage gaps for `tensordock` should always be inspected before being interpreted as a market signal. |

Providers that gpuhunt configures but which require an API key not
present in the CI environment are skipped silently; the cron logs
include `Skipping provider X: Set the X_API_KEY environment variable.`
Currently this affects HotAisleProvider and DigitalOceanProvider.

Providers worth adding (not yet supported): CoreWeave, Crusoe, Together,
Modal, Replicate, Fluidstack, Paperspace. Most require API keys or
custom scraping; tracked in the project roadmap.

## 6. Normalization

What we normalize:

- **`provider`**: lowercased and mapped through a small alias table in
  `collect.py:159-171`.
- **`gpu_type`**: gpuhunt produces normalized accelerator family names
  (e.g. `H100`, `A100`, `L40S`, `RTX4090`). We use these as-is. We have
  not observed casing variants in the wild.
- **`price_per_hour`**: assumed USD. All currently supported providers
  publish in USD; no FX conversion is applied. Adding a non-USD provider
  in the future will require a `currency` column.

What we do **not** normalize:

- **`region`**: raw provider region strings are stored verbatim (`us-east-1`
  on AWS, `us-east1` on GCP, `eastus` on Azure, `US-ASHBURN-1` on OCI,
  `EUR-IS-2` on Vultr, etc.). Cross-provider regional comparisons
  therefore require a separate lookup table — building this is on the
  roadmap. Until then, regional analyses should restrict to a single
  provider, or filter the raw strings explicitly.
- **`is_spot` semantics**: see §7.

## 7. Spot semantics by provider

The `is_spot` boolean is faithful to the upstream `gpuhunt` flag, but
the *meaning* of "spot" differs across providers. Modeling work that
treats the spot signal as a clean utilization proxy should be aware:

| Provider | Spot mechanism |
| --- | --- |
| `aws` | Auction-cleared spot pool with deterministic 2-minute interrupt warning. Price moves with capacity. |
| `gcp` | Preemptible VMs / Spot VMs with up to 24-hour lifetime and 30-second interrupt warning. Discount is largely fixed (~60–91% off on-demand). |
| `azure` | Spot VMs with eviction policy controlled by user; price is a published rate, not auction. |
| `runpod` | "Community Cloud" listings are spot-equivalent: low-cost, interruptible, hosted by independent providers. |
| `vastai` | Peer-to-peer marketplace; "interruptible" listings can be reclaimed by the host at any time. Closer to a P2P bidding market than a hyperscaler auction. |
| `cudo` | Decentralized provider; spot listings are interruptible. |

For analyses that require a single, comparable spot definition,
restrict to hyperscaler spot (`provider IN ('aws', 'gcp', 'azure')`) and
treat marketplace providers separately.

## 8. Quality flags and known issues

- **CPU-only / unknown rows**: a non-trivial fraction of upstream
  responses are CPU-only instances or instances whose GPU `gpuhunt`
  cannot map. These appear as `gpu_count = 0` and/or
  `gpu_type = 'Unknown'`. The Streamlit dashboard filters them out by
  default; the raw Parquet currently still contains them. Adding a
  `quality` column at collection time is on the roadmap.
- **`available = false`**: a listing being scraped does not guarantee
  it can be launched. Some providers expose all SKUs and we infer
  availability where possible, but the field is best-effort.
- **Cron drift**: GitHub Actions cron schedules can drift by tens of
  minutes under load. The 09:00/21:00 UTC schedule should be read as
  "twice daily, ±30 min."

## 9. Limitations

- **No customer telemetry**: only listings, not consumption.
- **Sticky on-demand prices**: hyperscaler on-demand prices change on
  billing-cycle timescales, so on-demand series have low signal-to-noise
  for short-horizon demand inference. Marketplace spot prices are the
  load-bearing demand signal.
- **12-hour resolution**: insufficient for intraday auction analyses.
- **No reserved/committed-use pricing**: the dataset captures
  on-demand and spot only.
- **No bandwidth or storage costs**: total cost of ownership cannot be
  computed from this dataset alone for I/O- or data-heavy workloads.

For a fuller treatment of what modeling questions the data does and
does not support, see
[MODELING_GPU_USAGE_TRENDS.md](MODELING_GPU_USAGE_TRENDS.md).

## 10. License & citation

The dataset is released under **CC BY 4.0**; the source code under
**MIT**. See [LICENSE](LICENSE), [DATA_LICENSE](DATA_LICENSE), and
[CITATION.cff](CITATION.cff). Suggested attribution:

> Hubbard, A. (2026). *GPU Price Tracker dataset*.
> https://github.com/alex-hubbard/gpu_price_tracker (CC BY 4.0).
