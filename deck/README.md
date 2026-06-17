# GPU Rental Market — Slide Deck

A self-contained presentation built from the `gpu_price_tracker` Parquet dataset
(Jan 12 – Jun 15 2026; 802K GPU listings, 13 providers, 72 GPU types).

## View it

Open **`gpu_market_deck.html`** in any browser — no internet or server needed
(charts are embedded as base64). Navigate with arrow keys / space, click left or
right half to step, `f` for fullscreen.

## Files

| File | What it is |
| --- | --- |
| `gpu_market_deck.html` | The deck — 15 slides, fully self-contained |
| `analyze.py` | Pricing/spot/provider analysis over `data/parquet/` → `findings.json` + `figures/01–06` |
| `geo_analysis.py` | US geographic analysis (maps + heatmap) → `geo_findings.json` + `figures/07–09` |
| `build_deck.py` | Assembles the HTML deck from both findings files and `figures/` |
| `findings.json`, `geo_findings.json` | All computed numbers cited in the deck |
| `figures/*.png` | Source charts |

## Reproduce

```bash
python3 deck/analyze.py       # pricing figures + findings.json
python3 deck/geo_analysis.py  # US map figures + geo_findings.json
python3 deck/build_deck.py    # rebuild the HTML deck
```

US maps use the continental-US outline bundled with `geopandas`
(`naturalearth_lowres`), so no network access is required.

## Headline findings

- **Provider choice is the biggest lever:** the same H100 ranges from ~$1.61/GPU-hr
  (Vast.ai) to ~$10.98/GPU-hr (GCP) — a **6.8×** spread.
- **Spot saves ~45–70%**, but the discount compresses on scarce frontier silicon
  (H100/H200 ≈ 45–49%) vs. commodity GPUs (T4/A10 ≈ 70%+).
- **17× ladder** from B200 (~$6.69) down to RTX 4090 (~$0.39).
- On-demand prices are **sticky**; a 60-day scraper gap splits the series into two
  epochs (never interpolated across).
- **US supply is concentrated:** the top 3 metros (Virginia, Iowa, Oregon) hold ~47%
  of all geocoded US listings; newer silicon (B200) is thin and clustered while
  commodity T4s blanket the map.

## Caveat

The dataset measures **price and inventory**, not consumed GPU-hours — all "usage"
statements are inferences from those proxies. See `../MODELING_GPU_USAGE_TRENDS.md`.
