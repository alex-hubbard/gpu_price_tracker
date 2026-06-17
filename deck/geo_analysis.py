#!/usr/bin/env python3
"""Geographic analysis of US GPU supply -> maps + heatmap for the deck."""
import duckdb, json, warnings
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
warnings.filterwarnings("ignore")

plt.rcParams.update({"figure.dpi": 140, "font.size": 11, "font.family": "DejaVu Sans"})
FIG = "deck/figures"
con = duckdb.connect()
con.execute("CREATE TABLE regions AS SELECT * FROM read_csv_auto('data/regions.csv')")
P = "read_parquet('data/parquet/prices/**/*.parquet', hive_partitioning=1)"

# US outline (lower-48 clip) from geopandas' bundled Natural Earth dataset.
# Clip to the continental bbox first — the raw USA polygon includes Alaska's
# Aleutians (which cross the antimeridian) and Hawaii, wrecking the aspect.
world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
usa = world[world.name == "United States of America"]
BBOX = dict(lon=(-125, -66.5), lat=(24, 49.5))
from shapely.geometry import box as _box
usa_clip = gpd.clip(usa, _box(BBOX["lon"][0], BBOX["lat"][0], BBOX["lon"][1], BBOX["lat"][1]))

def base_map(ax):
    usa_clip.plot(ax=ax, color="#eef1f7", edgecolor="#aab4cc", lw=0.9, zorder=0)
    ax.set_xlim(*BBOX["lon"]); ax.set_ylim(*BBOX["lat"])  # keep geopandas' geographic aspect
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)

# nice short labels for metros
NAME = lambda m: (m.replace("us-east-","").replace("us-west-","").replace("us-central-","")
                   .replace("us-south-","").replace("us-north-","").replace("us-gov-","gov:")
                   .replace("-att","").replace("saltlakecity","saltlake").title())

BASE = f"""
  SELECT g.gpu_type, g.is_spot, g.price_per_hour/g.gpu_count AS ppgh,
         regexp_replace(r.region_canonical,'-zone$','') AS metro, r.lat, r.lon
  FROM {P} g JOIN regions r ON g.provider=r.provider AND g.region=r.raw_region
  WHERE r.country='US' AND r.region_canonical IS NOT NULL
    AND g.gpu_count>0 AND g.price_per_hour>0 AND g.gpu_type<>'Unknown'
"""
con.execute(f"CREATE TABLE us AS WITH j AS ({BASE}) SELECT * FROM j")

findings = {}

# ---------- FIG 7: headline supply map (cluster by coordinate) ----------
clu = con.execute("""
  SELECT ROUND(lat,2) lat, ROUND(lon,2) lon, COUNT(*) listings,
         COUNT(DISTINCT gpu_type) gtypes,
         arg_max(metro, cnt) metro
  FROM (SELECT lat,lon,metro,gpu_type, COUNT(*) OVER (PARTITION BY ROUND(lat,2),ROUND(lon,2),metro) cnt FROM us)
  GROUP BY 1,2 ORDER BY listings DESC""").df()
# merge identical coords keeping largest metro label
agg = con.execute("""
  SELECT ROUND(lat,2) lat, ROUND(lon,2) lon, COUNT(*) listings, COUNT(DISTINCT gpu_type) gtypes
  FROM us GROUP BY 1,2 ORDER BY listings DESC""").df()
fig, ax = plt.subplots(figsize=(10, 6.2))
base_map(ax)
sizes = (agg["listings"] / agg["listings"].max() * 2600) + 30
sc = ax.scatter(agg["lon"], agg["lat"], s=sizes, c=agg["gtypes"], cmap="plasma",
                alpha=0.78, edgecolor="white", lw=0.7, zorder=5, vmin=0)
# label the biggest hubs
big = con.execute("""SELECT ROUND(lat,2) lat, ROUND(lon,2) lon, arg_max(metro,n) metro, SUM(n) listings
  FROM (SELECT lat,lon,metro,COUNT(*) n FROM us GROUP BY 1,2,3) GROUP BY 1,2
  ORDER BY listings DESC LIMIT 9""").df()
for r in big.itertuples():
    ax.text(r.lon, r.lat, f"{NAME(r.metro)}\n{int(r.listings/1000)}K",
            fontsize=7.5, ha="center", va="center", fontweight="bold", color="#0b1020", zorder=6)
cb = fig.colorbar(sc, ax=ax, fraction=0.025, pad=0.01)
cb.set_label("distinct GPU types at site", fontsize=9)
ax.set_title("US GPU supply: bubble = listing volume, color = GPU variety", fontsize=14, fontweight="bold")
plt.tight_layout(); plt.savefig(f"{FIG}/07_us_supply_map.png", bbox_inches="tight"); plt.close()
print("wrote 07_us_supply_map")
findings["top_hubs"] = [{"metro": NAME(r.metro), "listings": int(r.listings)} for r in big.itertuples()]

# ---------- FIG 8: GPU family x metro heatmap ----------
top_metros = con.execute("SELECT metro FROM us GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 12").df()["metro"].tolist()
top_gpus = con.execute("""SELECT gpu_type FROM us
  WHERE gpu_type IN ('B200','H200','H100','L40S','A100','A10','L4','T4','V100','P100','RTXPRO6000','A6000','GH200')
  GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 11""").df()["gpu_type"].tolist()
ml = "','".join(top_metros); gl = "','".join(top_gpus)
mat = con.execute(f"""SELECT gpu_type, metro, COUNT(*) n FROM us
  WHERE metro IN ('{ml}') AND gpu_type IN ('{gl}') GROUP BY 1,2""").df()
M = mat.pivot(index="gpu_type", columns="metro", values="n").reindex(index=top_gpus, columns=top_metros)
Mv = M.fillna(0).values
fig, ax = plt.subplots(figsize=(11, 6))
norm = LogNorm(vmin=1, vmax=np.nanmax(Mv))
im = ax.imshow(np.where(Mv>0, Mv, np.nan), aspect="auto", cmap="viridis", norm=norm)
ax.set_xticks(range(len(top_metros))); ax.set_xticklabels([NAME(m) for m in top_metros], rotation=40, ha="right", fontsize=9)
ax.set_yticks(range(len(top_gpus))); ax.set_yticklabels(top_gpus, fontsize=9)
for i in range(len(top_gpus)):
    for j in range(len(top_metros)):
        v = Mv[i, j]
        if v > 0:
            ax.text(j, i, f"{int(v/1000)}K" if v>=1000 else int(v), ha="center", va="center",
                    fontsize=7, color="white" if v < np.nanmax(Mv)*0.3 else "black")
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01); cb.set_label("listings (log)", fontsize=9)
ax.set_title("Where each GPU lives: listings by family × US metro", fontsize=14, fontweight="bold")
ax.set_xlabel(""); ax.set_ylabel("")
plt.tight_layout(); plt.savefig(f"{FIG}/08_gpu_metro_heatmap.png", bbox_inches="tight"); plt.close()
print("wrote 08_gpu_metro_heatmap")

# ---------- FIG 9: per-GPU footprint small multiples ----------
marquee = ["B200", "H100", "A100", "T4"]
fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
for ax, g in zip(axes.flat, marquee):
    base_map(ax)
    d = con.execute(f"""SELECT ROUND(lat,2) lat, ROUND(lon,2) lon, COUNT(*) n
        FROM us WHERE gpu_type='{g}' GROUP BY 1,2""").df()
    if not d.empty:
        s = (d["n"]/d["n"].max()*900)+25
        ax.scatter(d["lon"], d["lat"], s=s, color="#2563eb", alpha=0.65, edgecolor="white", lw=0.6, zorder=5)
    st = con.execute(f"SELECT COUNT(*) n, COUNT(DISTINCT metro) locs FROM us WHERE gpu_type='{g}'").fetchone()
    ax.set_title(f"{g}  ·  {int(st[0]):,} listings across {int(st[1])} metros", fontsize=11, fontweight="bold")
fig.suptitle("Geographic footprint by GPU generation", fontsize=14, fontweight="bold", y=0.99)
plt.tight_layout(); plt.savefig(f"{FIG}/09_gpu_footprints.png", bbox_inches="tight"); plt.close()
print("wrote 09_gpu_footprints")

# footprint stats
for g in marquee:
    r = con.execute(f"SELECT COUNT(*) n, COUNT(DISTINCT metro) locs FROM us WHERE gpu_type='{g}'").fetchone()
    findings.setdefault("footprints", {})[g] = {"listings": int(r[0]), "sites": int(r[1])}

# concentration: top-3 metro share of all US listings
conc = con.execute("""WITH m AS (SELECT metro, COUNT(*) n FROM us GROUP BY 1)
  SELECT SUM(n) tot, (SELECT SUM(n) FROM (SELECT n FROM m ORDER BY n DESC LIMIT 3)) top3 FROM m""").fetchone()
findings["concentration"] = {"top3_share_pct": round(100*conc[1]/conc[0], 1),
                             "n_metros": int(con.execute("SELECT COUNT(DISTINCT metro) FROM us").fetchone()[0])}

json.dump(findings, open("deck/geo_findings.json", "w"), indent=2)
print(json.dumps(findings, indent=2))
