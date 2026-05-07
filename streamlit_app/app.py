"""GPU Price Tracker — public Streamlit dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from queries import (  # noqa: E402
    load_filter_options,
    load_latest_snapshot,
    load_spread,
    load_stats,
    load_trends,
)

st.set_page_config(
    page_title="GPU Price Tracker",
    page_icon="💸",
    layout="wide",
)

st.title("GPU Price Tracker")
st.caption(
    "Cross-cloud GPU rental prices, collected twice daily across "
    "AWS, GCP, Azure, Lambda, RunPod, Vast.ai, and other providers."
)

stats = load_stats()
options = load_filter_options()
latest = load_latest_snapshot()

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
tab_table, tab_trends, tab_spread = st.tabs(
    ["Latest prices", "Price trends", "Spot vs on-demand"]
)

# ----- Tab 1: Latest prices -----
with tab_table:
    df = latest.copy()
    if gpu_filter:
        df = df[df["gpu_type"].isin(gpu_filter)]
    if provider_filter:
        df = df[df["provider"].isin(provider_filter)]
    if is_spot_filter is not None:
        df = df[df["is_spot"] == is_spot_filter]

    df = df.sort_values("price_per_gpu_hour")
    st.write(f"**{len(df):,}** matching listings")
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

st.divider()
st.caption(
    f"Data refreshed twice daily • last snapshot {stats['last_snapshot']} • "
    "[source on GitHub](https://github.com/alex-hubbard/gpu_price_tracker)"
)
