# Modeling GPU Usage Trends from This Dataset

This document explains what the `gpu_price_tracker` pipeline actually captures, how those observations relate to GPU *usage*, and which modeling questions the data is — and is not — positioned to answer. It is written for someone planning to build forecasts, elasticity models, or market-tightness indicators on top of the SQLite store in `data/gpu_prices.db`.

## 1. What is actually captured

The pipeline scrapes `gpuhunt` twice daily (09:00 and 21:00 local, via `daily_update.sh`) and writes one row per cloud listing into `gpu_prices`:

| Column | Meaning | Role in modeling |
| --- | --- | --- |
| `timestamp` | Collection time (snapshot id) | Panel time index |
| `provider` | 13+ clouds (aws, gcp, azure, lambda, runpod, vastai, …) | Entity / fixed effect |
| `instance_type` | Provider-specific SKU | Finest listing grain |
| `gpu_type` | Normalized accelerator family (H100, A100, L40S, RTX4090, …) | Primary grouping for demand modeling |
| `gpu_count`, `gpu_memory_gb` | Accelerators per SKU and their VRAM | Capacity feature; enables `price_per_gpu_hour` |
| `vcpus`, `ram_gb` | Host specs | Controls for bundled-resource effects |
| `region` | Cloud region string | Geographic effect; cross-region arbitrage |
| `price_per_hour` | USD/hour for the full SKU | Core dependent variable |
| `is_spot` | Spot/preemptible flag | Separates supply-sensitive from list prices |
| `available`, `availability_zone` | Offered / not offered | Censoring signal |

The unique key is `(timestamp, provider, instance_type, region, is_spot)`, so the natural shape is an **unbalanced panel** of listings observed roughly every 12 hours. A parallel `price_snapshots` table stores per-timestamp aggregates (total instances, min/max/avg price, provider and GPU-type counts), which is useful as a sanity baseline when listing coverage wobbles.

## 2. "Usage" vs. what we observe

Nothing in this dataset measures GPU hours actually consumed by customers. What it *does* measure are two proxies that move with demand:

1. **Price signal** — especially spot prices on marketplaces (`vastai`, `runpod`, `tensordock`, and AWS/GCP spot). On a spot market, price is an instantaneous clearing signal for supply–demand imbalance, so changes in the spot distribution are a direct read on utilization pressure. On-demand list prices move much more slowly and reflect posted rather than cleared pricing.
2. **Listing/inventory signal** — the count of offered instances per `(gpu_type, provider, region)` tracks how much capacity providers are exposing to the market. Marketplaces that list only free inventory (Vast.ai, RunPod) effectively publish "unused capacity"; the *complement* of that count is a usage proxy.

Both proxies are strongest on the marketplace providers and weakest on hyperscalers, where on-demand listings are effectively always "available" and prices move on billing-cycle timescales.

Treat the dataset as a **market-microstructure view of the GPU rental market**. That frames both the usable modeling questions and the limits below.

## 3. Modeling questions the data supports

### 3.1 Price-level forecasting per GPU family
- **Target:** `avg price_per_gpu_hour` or spot-price quantiles for a given `gpu_type`, possibly conditioned on `(provider, region, is_spot)`.
- **Why feasible:** `get_price_trends()` already emits the (timestamp, avg/min/max, instance_count) series per GPU family. With twice-daily cadence, short-horizon ARIMA/ETS or gradient-boosted regression with lag features is the natural first pass; hierarchical models (e.g., `prophet` with GPU-family grouping, or a mixed-effects regression with `(provider, region)` random effects) exploit the panel structure.
- **Useful features:** lagged price, lagged instance count, spot–on-demand spread, rolling coefficient of variation across providers, day-of-week and time-of-day dummies (captures the 09:00/21:00 collection cycle and any weekly business-hour effect).

### 3.2 Supply-side capacity tracking
- **Target:** `COUNT(*) GROUP BY timestamp, gpu_type, provider` — how many SKUs each provider is exposing for a given accelerator.
- **What it models:** provider-level inventory trajectories. A sustained rise in listed H100 instances across marketplaces typically means newer deployments are coming online or utilization is softening; a sustained fall with concurrent spot-price increases points to tightening.
- **Watch out for:** scraper gaps. The recent daily logs (e.g., `data/daily_update_20260421_0900.log`) show `gpuhunt` not installed in the current environment, so the last successful snapshot is `2026-04-02`. Any model must detect and handle these dropouts, otherwise a collection outage will be misread as a capacity cliff.

### 3.3 Spot–on-demand spread as a utilization proxy
- **Target:** for each `(gpu_type, region, provider)` with both spot and on-demand listings, compute `spread = on_demand_price − spot_price` or the ratio.
- **Why it works:** spot discounts widen when utilization is low (surplus capacity) and compress when demand is high. This is the most defensible single-feature "usage tightness" index the dataset can produce, because it is robust to listing-count measurement noise and to cross-provider price-level differences.
- **Implementation note:** join on `(timestamp, provider, instance_type, region)` across `is_spot = 0/1`. Not every SKU has both; an H100 spot index will only exist where a cloud actually exposes H100 spot.

### 3.4 Regional demand concentration and arbitrage
- **Target:** price dispersion across `region` for a fixed `(provider, gpu_type)` — e.g., coefficient of variation, or `us-east-1` vs. `eu-west` gap.
- **What it models:** which regions are running hot. Existing plots (`aws_gcp_regional_heatmap.png`, `aws_gcp_regional_gpu_variations.png`) already surface this; the modeling layer would turn it into a time-indexed index and test for persistence.
- **Useful for:** scheduling / cost-optimization recommenders, and for detecting when new regional capacity comes online (sudden compression of the gap).

### 3.5 Cross-provider price co-movement
- **Target:** correlation matrix / factor model across providers for a fixed `gpu_type`.
- **What it models:** whether GPU pricing is driven by a shared demand factor (common shocks across AWS, GCP, Lambda, RunPod) or by idiosyncratic provider behavior. A one-factor model whose loadings concentrate on hyperscalers would suggest that marketplace providers front-run aggregate demand shifts; a uniform loading profile would suggest a shared "H100 tightness" factor.
- **Modeling tools:** PCA on the (time × provider) price panel per GPU family; dynamic factor models if horizons get longer than a few months.

### 3.6 Generational substitution and obsolescence curves
- **Target:** the relative price gap between generations (H200 vs. H100, RTX 5090 vs. 4090 vs. 3090) over time.
- **What it models:** the rate at which the market re-prices older accelerators as a new generation ships. This is directly actionable for buyers choosing between a currently-cheap A100 and a more expensive H100.
- **Feasible because:** the catalog already covers 55+ GPU types including legacy (V100, P100, T4), current data-center (H100, H200, A100, L40S), and consumer (RTX 3090/4090/5090) parts side-by-side.

### 3.7 Event detection / change-point analysis
- **Target:** structural breaks in price or listing counts.
- **Why it matters:** new model launches, provider capacity expansions, export-control news, and supply shocks all show up as regime shifts. A Bayesian change-point detector on the spot-price series per GPU family would flag these without needing labels.

## 4. Feature engineering checklist

When building a model on this data, the following transforms tend to be load-bearing:

- Normalize to **price per GPU hour** (`price_per_hour / gpu_count`) before comparing SKUs; the codebase already exposes this as `GPUInstance.price_per_gpu_hour`.
- Split `is_spot = 0` vs. `is_spot = 1` into separate series — they respond to different forces.
- Deduplicate provider names early; `collect.py` maps common aliases but the dataset still contains tail providers that should be either kept distinct or bucketed into a single "marketplace" class.
- Use `gpu_memory_gb` as a continuous feature rather than `gpu_type` as the sole identifier when modeling across GPU families; it absorbs much of the VRAM-driven price variance.
- Treat missing snapshots as missing data, not zero — fill only within-day gaps, and flag multi-day collection outages so downstream models can mask them.

## 5. Limits of the data

These are hard limits, not tuning problems:

- **No customer-side telemetry.** We never observe actual rented hours, concurrency, or utilization per tenant. Any "usage" conclusion is inferred from price and listing counts.
- **On-demand prices are sticky.** For hyperscalers, `price_per_hour` for a non-spot SKU can be constant across many snapshots. Models that lean on hyperscaler on-demand prices as a demand signal will underperform models that lean on marketplace spot series.
- **Listing count is coverage-dependent.** A drop can mean a provider delisted SKUs *or* that `gpuhunt` failed to scrape them. The `price_snapshots` table's `providers_count` is the first thing to check before attributing any change to market behavior.
- **12-hour granularity is coarse.** Intraday demand spikes and marketplace auction dynamics are smoothed out. Short-horizon forecasting below a day is not supported; reducing the collection interval would help, as would snapshotting spot marketplaces more aggressively than hyperscalers.
- **Region strings are not geocoded.** Cross-provider regional comparisons require a mapping layer (e.g., `us-east-1` ↔ `us-east1` ↔ `virginia`) that the current pipeline does not maintain.
- **Spot flag reliability varies.** The `is_spot` column is populated from `gpuhunt`'s `spot` attribute; marketplaces that do not cleanly separate spot from reserved listings will be noisy here.

## 6. What to add to strengthen the modeling story

If the goal is genuine *usage* modeling rather than price/inventory modeling, consider augmenting the data with:

- **Provider-published capacity or utilization disclosures** (e.g., AWS capacity-reservation availability, CoreWeave / Lambda status pages).
- **Public demand proxies**: Hugging Face model download counts, PyPI download counts for CUDA wheels, GitHub stars on inference frameworks — all correlate with training/inference demand at the population level.
- **Event timeline**: a hand-curated table of launch dates (H100 GA, H200 GA, Blackwell rollouts), export-control changes, and major provider capacity announcements. Without this, any structural break the model finds will be unlabeled.
- **Higher-frequency spot snapshots** on marketplace providers (e.g., every 30 minutes) without increasing load on hyperscaler scraping, which doesn't benefit from it.

## 7. Starter queries

```sql
-- Per-day average spot price for H100 across all marketplace providers
SELECT DATE(timestamp) AS day,
       AVG(price_per_hour / gpu_count) AS avg_price_per_gpu_hour,
       COUNT(*) AS listings
FROM gpu_prices
WHERE gpu_type = 'H100' AND is_spot = 1
GROUP BY day
ORDER BY day;

-- Spot vs. on-demand spread per provider for A100
SELECT DATE(s.timestamp) AS day, s.provider,
       AVG(od.price_per_hour) - AVG(s.price_per_hour) AS spread
FROM gpu_prices s
JOIN gpu_prices od
  ON s.timestamp = od.timestamp
 AND s.provider = od.provider
 AND s.instance_type = od.instance_type
 AND s.region = od.region
 AND s.is_spot = 1 AND od.is_spot = 0
WHERE s.gpu_type = 'A100'
GROUP BY day, s.provider
ORDER BY day, s.provider;

-- Regional dispersion index for a GPU family
SELECT DATE(timestamp) AS day, region,
       AVG(price_per_hour / gpu_count) AS avg_price_per_gpu_hour
FROM gpu_prices
WHERE gpu_type = 'L40S' AND provider = 'aws'
GROUP BY day, region
ORDER BY day, region;
```

The `database.py` helpers (`get_price_trends`, `get_price_history`, `get_snapshots`) cover the equivalent aggregations in Python and are the right entry points for notebook work; `analysis.ipynb` and `aws_gcp_analysis.ipynb` already contain templates for trend plotting, regional heatmaps, and spot-savings analysis that can be extended into formal models.
