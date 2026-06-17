"""GPU Price Tracker — public Streamlit dashboard."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from queries import (  # noqa: E402
    load_filter_options,
    load_latest_snapshot,
    load_provider_freshness,
    load_regional_dispersion,
    load_spread,
    load_stats,
    load_trends,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DECK_PATH = REPO_ROOT / "deck" / "gpu_market_deck.html"
GITHUB_URL = "https://github.com/alex-hubbard/gpu_price_tracker"
PUBLIC_S3_URL = "s3://hubbard-gpu-price-data/prices/"
HF_DATASET_URL = "https://huggingface.co/datasets/afhubbard/gpu-prices"

st.set_page_config(
    page_title="GPU Price Tracker",
    page_icon="💸",
    layout="wide",
)

st.title("GPU Price Tracker")
st.caption(
    "Cross-cloud GPU rental prices, collected twice daily across "
    "AWS, GCP, Azure, Lambda, RunPod, Vast.ai, and other providers. "
    f"[Source on GitHub]({GITHUB_URL})."
)

stats = load_stats()
options = load_filter_options()
latest = load_latest_snapshot()
freshness = load_provider_freshness()


# ---------- Freshness banner ----------
def _freshness_banner(last_snapshot_iso: str | None) -> None:
    if not last_snapshot_iso:
        st.error("No data available.")
        return
    last = pd.to_datetime(last_snapshot_iso, utc=True)
    now = datetime.now(timezone.utc)
    age = now - last.to_pydatetime()
    age_h = age.total_seconds() / 3600
    last_str = last.strftime("%Y-%m-%d %H:%M UTC")
    if age_h <= 24:
        st.success(
            f"🟢 Fresh — last collected {last_str} ({age_h:.1f}h ago)."
        )
    elif age_h <= 72:
        st.warning(
            f"🟡 Stale — last collected {last_str} ({age_h:.0f}h ago). "
            "Daily collection may have missed a run."
        )
    else:
        st.error(
            f"🔴 Outdated — last collected {last_str} "
            f"({age_h / 24:.1f} days ago). Pipeline likely broken."
        )


_freshness_banner(stats["last_snapshot"])

# ---------- KPI row ----------
kpi_cols = st.columns(6)
kpi_cols[0].metric("Last snapshot", stats["last_snapshot"] or "—")
kpi_cols[1].metric("Snapshots", f"{stats['snapshots']:,}")
kpi_cols[2].metric("Listings (latest)", f"{len(latest):,}")
kpi_cols[3].metric("Providers", stats["providers"])
kpi_cols[4].metric("GPU types", stats["gpu_types"])
if not latest.empty:
    kpi_cols[5].metric(
        "Median $/GPU-hr",
        f"${latest['price_per_gpu_hour'].median():.2f}",
    )

# ---------- Per-provider freshness panel ----------
if not freshness.empty:
    last_snapshot_ts = pd.to_datetime(stats["last_snapshot"], utc=True)
    with st.expander("Per-provider coverage", expanded=False):
        st.caption(
            "🟢 listed in the latest snapshot · "
            "🟡 not in latest, but seen in the last 7 days · "
            "🔴 not seen in the last 7 days (likely scraper outage)"
        )
        cols = st.columns(min(len(freshness), 6))
        for i, row in freshness.reset_index(drop=True).iterrows():
            seen = pd.to_datetime(row["last_seen"], utc=True)
            age_h = (last_snapshot_ts - seen).total_seconds() / 3600
            if int(row["listings_in_latest"]) > 0:
                dot = "🟢"
            elif age_h <= 7 * 24:
                dot = "🟡"
            else:
                dot = "🔴"
            with cols[i % len(cols)]:
                st.markdown(
                    f"{dot} **{row['provider']}**  \n"
                    f"<span style='color:#888;font-size:0.85em'>"
                    f"{int(row['listings_in_latest']):,} in latest · "
                    f"{seen.strftime('%Y-%m-%d %H:%M UTC')}"
                    f"</span>",
                    unsafe_allow_html=True,
                )

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
gpu_filter = st.sidebar.multiselect(
    "GPU types",
    options=options["gpu_types"],
    default=[],
    help="Empty = all GPUs",
)
provider_filter = st.sidebar.multiselect(
    "Providers",
    options=options["providers"],
    default=[],
    help="Empty = all providers",
)
region_group_filter = st.sidebar.multiselect(
    "Region group",
    options=options.get("region_groups", []),
    default=[],
    help="Empty = all region groups (continental buckets across providers)",
)
spot_choice = st.sidebar.radio(
    "Pricing type",
    ["Both", "On-demand only", "Spot only"],
    index=0,
)
lookback_days = st.sidebar.slider(
    "Lookback (days)", min_value=7, max_value=180, value=30, step=1
)

is_spot_filter: bool | None = None
if spot_choice == "Spot only":
    is_spot_filter = True
elif spot_choice == "On-demand only":
    is_spot_filter = False

# ---------- Tabs ----------
@st.cache_data(show_spinner=False)
def _load_deck() -> str | None:
    """Read the self-contained slide deck HTML bundled in the repo, if present."""
    if DECK_PATH.exists():
        return DECK_PATH.read_text(encoding="utf-8")
    return None


tab_table, tab_trends, tab_spread, tab_region, tab_deck, tab_about = st.tabs(
    [
        "Latest prices",
        "Price trends",
        "Spot vs on-demand",
        "Regional dispersion",
        "Market analysis",
        "About / Methodology",
    ]
)

# ----- Tab 1: Latest prices -----
with tab_table:
    df = latest.copy()
    if gpu_filter:
        df = df[df["gpu_type"].isin(gpu_filter)]
    if provider_filter:
        df = df[df["provider"].isin(provider_filter)]
    if region_group_filter:
        df = df[df["region_group"].isin(region_group_filter)]
    if is_spot_filter is not None:
        df = df[df["is_spot"] == is_spot_filter]

    df = df.sort_values("price_per_gpu_hour")

    header_col, dl_col = st.columns([4, 1])
    header_col.write(f"**{len(df):,}** matching listings")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    dl_col.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=f"gpu_prices_{stats['last_snapshot'][:10]}.csv"
        if stats["last_snapshot"]
        else "gpu_prices.csv",
        mime="text/csv",
        use_container_width=True,
        help="Download the currently filtered listings as CSV.",
    )

    st.dataframe(
        df[
            [
                "provider",
                "instance_type",
                "gpu_type",
                "gpu_count",
                "gpu_memory_gb",
                "vcpus",
                "ram_gb",
                "region",
                "region_canonical",
                "region_group",
                "country",
                "is_spot",
                "price_per_hour",
                "price_per_gpu_hour",
                "available",
            ]
        ],
        column_config={
            "price_per_hour": st.column_config.NumberColumn(
                "$/hr", format="$%.4f"
            ),
            "price_per_gpu_hour": st.column_config.NumberColumn(
                "$/GPU-hr", format="$%.4f"
            ),
            "is_spot": st.column_config.CheckboxColumn("Spot"),
            "available": st.column_config.CheckboxColumn("Available"),
            "gpu_memory_gb": st.column_config.NumberColumn("VRAM (GB)"),
            "ram_gb": st.column_config.NumberColumn("RAM (GB)"),
            "region": st.column_config.TextColumn("Raw region"),
            "region_canonical": st.column_config.TextColumn("Canonical region"),
            "region_group": st.column_config.TextColumn("Group"),
            "country": st.column_config.TextColumn("Country"),
        },
        hide_index=True,
        use_container_width=True,
    )

# ----- Tab 2: Price trends -----
with tab_trends:
    if not gpu_filter:
        # Default: top 6 most-listed GPU families so the chart isn't empty
        default_gpus = tuple(options["gpu_types"][:6])
        st.info(
            "Showing the 6 most-listed GPU families. "
            "Use the sidebar to filter to specific GPUs."
        )
    else:
        default_gpus = tuple(gpu_filter)

    trends = load_trends(
        gpu_types=default_gpus,
        providers=tuple(provider_filter),
        region_groups=tuple(region_group_filter),
        is_spot=is_spot_filter,
        days=lookback_days,
    )

    if trends.empty:
        st.warning(
            "No data in the selected window. "
            "Try a longer lookback or different filters."
        )
    elif trends["day"].nunique() < 2:
        st.warning(
            "Only one snapshot day in this window — "
            "trends need at least two days of history. "
            f"Latest snapshot: {stats['last_snapshot']}."
        )
        st.dataframe(trends, hide_index=True, use_container_width=True)
    else:
        fig = px.line(
            trends,
            x="day",
            y="avg_price_per_gpu_hour",
            color="gpu_type",
            markers=True,
            labels={
                "day": "Date",
                "avg_price_per_gpu_hour": "Avg $/GPU-hr",
                "gpu_type": "GPU",
            },
            title="Average price per GPU-hour over time",
        )
        fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        listings_fig = px.line(
            trends,
            x="day",
            y="listings",
            color="gpu_type",
            labels={"day": "Date", "listings": "Listings", "gpu_type": "GPU"},
            title="Listing count over time (supply proxy)",
        )
        listings_fig.update_layout(hovermode="x unified")
        st.plotly_chart(listings_fig, use_container_width=True)

# ----- Tab 3: Spot vs on-demand spread -----
with tab_spread:
    st.markdown(
        "On-demand minus spot price per GPU-hour, by provider. "
        "Wider spreads suggest looser utilization (spot deeply discounted); "
        "narrower spreads suggest tightening demand. "
        "See `MODELING_GPU_USAGE_TRENDS.md` for the full rationale."
    )

    spread_gpu = st.selectbox(
        "GPU family",
        options=options["gpu_types"],
        index=options["gpu_types"].index("H100")
        if "H100" in options["gpu_types"]
        else 0,
    )
    spread = load_spread(spread_gpu, days=lookback_days)

    if spread.empty:
        st.warning(
            f"No matched spot/on-demand pairs for **{spread_gpu}** in the last "
            f"{lookback_days} days. Many GPUs are listed on-demand only on some "
            "providers, so the spread is undefined for them."
        )
    elif spread["day"].nunique() < 2:
        st.warning(
            "Only one snapshot day for this GPU — "
            "need at least two for a trend line."
        )
        st.dataframe(spread, hide_index=True, use_container_width=True)
    else:
        fig = px.line(
            spread,
            x="day",
            y="spread",
            color="provider",
            markers=True,
            labels={
                "day": "Date",
                "spread": "On-demand − Spot ($/GPU-hr)",
                "provider": "Provider",
            },
            title=f"{spread_gpu}: spot vs on-demand spread",
        )
        fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Underlying daily prices"):
            st.dataframe(spread, hide_index=True, use_container_width=True)

# ----- Tab 4: Regional dispersion -----
with tab_region:
    st.markdown(
        "Daily $/GPU-hour for one GPU family across the regions a single "
        "provider exposes it in. Wide spreads mean the buyer can save by "
        "moving regions; tight spreads mean the provider is uniformly "
        "priced. Per `MODELING_GPU_USAGE_TRENDS.md` §3.4."
    )

    rd_cols = st.columns(2)
    rd_provider = rd_cols[0].selectbox(
        "Provider",
        options=options["providers"],
        index=options["providers"].index("aws")
        if "aws" in options["providers"]
        else 0,
        key="rd_provider",
    )
    rd_gpu = rd_cols[1].selectbox(
        "GPU family",
        options=options["gpu_types"],
        index=options["gpu_types"].index("H100")
        if "H100" in options["gpu_types"]
        else 0,
        key="rd_gpu",
    )

    rd = load_regional_dispersion(rd_gpu, rd_provider, days=lookback_days)
    if rd.empty:
        st.warning(
            f"No listings for **{rd_gpu}** on **{rd_provider}** in the last "
            f"{lookback_days} days."
        )
    else:
        # Per-region time series.
        fig = px.line(
            rd,
            x="day",
            y="avg_price_per_gpu_hour",
            color="region",
            labels={
                "day": "Date",
                "avg_price_per_gpu_hour": "Avg $/GPU-hr",
                "region": "Region",
            },
            title=f"{rd_provider} {rd_gpu}: $/GPU-hr by region",
        )
        fig.update_layout(yaxis_tickprefix="$", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # Per-day coefficient of variation: σ / μ across regions.
        # A higher CV means more arbitrage opportunity across regions.
        agg = (
            rd.groupby("day")["avg_price_per_gpu_hour"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        agg["cv"] = agg["std"] / agg["mean"]
        cv_fig = px.line(
            agg.dropna(subset=["cv"]),
            x="day",
            y="cv",
            markers=True,
            labels={
                "day": "Date",
                "cv": "Cross-region CV",
            },
            title=f"Regional dispersion (coefficient of variation, n≥2 regions)",
        )
        cv_fig.update_layout(hovermode="x unified")
        st.plotly_chart(cv_fig, use_container_width=True)

        with st.expander("Daily prices by region"):
            st.dataframe(rd, hide_index=True, use_container_width=True)


# ----- Tab 5: Market analysis (slide deck) -----
with tab_deck:
    import streamlit.components.v1 as components  # noqa: E402

    st.subheader("The GPU rental market, priced by the hour")
    st.caption(
        "A 15-slide read on cross-cloud GPU pricing, spot economics, and US "
        "supply geography, built from the full dataset. Use arrow keys or click "
        "the left/right half of a slide to navigate; press **f** for fullscreen."
    )
    deck_html = _load_deck()
    if deck_html:
        components.html(deck_html, height=680, scrolling=False)
        st.download_button(
            "Download deck (self-contained HTML)",
            data=deck_html,
            file_name="gpu_market_deck.html",
            mime="text/html",
        )
    else:
        st.info(
            "The slide deck is not bundled with this deployment. "
            f"Build it from the repo (`python3 deck/analyze.py && "
            f"python3 deck/geo_analysis.py && python3 deck/build_deck.py`) "
            f"or view the source on [GitHub]({GITHUB_URL}/tree/main/deck)."
        )


# ----- Tab 6: About / Methodology -----
with tab_about:
    st.subheader("Get the data")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"""
**Hugging Face Datasets**

```python
from datasets import load_dataset
ds = load_dataset("afhubbard/gpu-prices", split="train")
```

[{HF_DATASET_URL}]({HF_DATASET_URL})
"""
        )
    with col_b:
        st.markdown(
            f"""
**Public S3 (anonymous read)**

```python
import duckdb
con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs;")
con.sql(\"\"\"
SELECT * FROM read_parquet(
  '{PUBLIC_S3_URL}**/*.parquet',
  hive_partitioning = true
) LIMIT 5
\"\"\")
```
"""
        )

    st.divider()
    st.subheader("How to cite")
    st.code(
        """@misc{hubbard2026gpuprices,
  author       = {Alex Hubbard},
  title        = {GPU Price Tracker},
  year         = {2026},
  howpublished = {\\url{https://github.com/alex-hubbard/gpu_price_tracker}},
  note         = {Dataset and software, MIT (code) / CC BY 4.0 (data)}
}""",
        language="bibtex",
    )

    st.divider()
    st.subheader("Methodology")
    methodology_path = REPO_ROOT / "methodology.md"
    if methodology_path.exists():
        st.markdown(
            methodology_path.read_text(encoding="utf-8"),
            unsafe_allow_html=False,
        )
    else:
        st.info(
            "methodology.md is not bundled with this deployment. "
            f"Read it on [GitHub]({GITHUB_URL}/blob/main/methodology.md)."
        )

st.divider()
st.caption(
    f"Data refreshed twice daily • last snapshot {stats['last_snapshot']} • "
    f"[source on GitHub]({GITHUB_URL}) · "
    "code MIT, data CC BY 4.0"
)
