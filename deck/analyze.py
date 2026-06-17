#!/usr/bin/env python3
"""Analysis for GPU price-tracker slide deck. Generates figures + findings.json."""
import duckdb, json, datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

plt.rcParams.update({
    "figure.dpi": 140, "font.size": 11,
    "axes.grid": True, "grid.alpha": 0.25, "axes.edgecolor": "#cccccc",
    "font.family": "DejaVu Sans",
})
ACCENT = "#2563eb"; PALETTE = ["#2563eb","#dc2626","#059669","#d97706","#7c3aed","#0891b2","#db2777","#65a30d"]
FIG = "deck/figures"
con = duckdb.connect()
P = "read_parquet('data/parquet/prices/**/*.parquet', hive_partitioning=1)"
GPU = f"FROM {P} WHERE gpu_count>0 AND price_per_hour>0 AND gpu_type<>'Unknown'"
findings = {}

def save(name):
    plt.tight_layout(); plt.savefig(f"{FIG}/{name}.png", bbox_inches="tight"); plt.close()
    print("wrote", name)

# ---- headline numbers ----
row = con.execute(f'SELECT COUNT(*) n, COUNT(DISTINCT CAST(dt AS DATE)) "days", COUNT(DISTINCT provider) provs, COUNT(DISTINCT gpu_type) gtypes, MIN(CAST(dt AS DATE)) mn, MAX(CAST(dt AS DATE)) mx {GPU}').fetchone()
findings["headline"] = {"gpu_listings": int(row[0]), "days": int(row[1]), "providers": int(row[2]),
                        "gpu_types": int(row[3]), "start": str(row[4]), "end": str(row[5])}
tot = con.execute(f"SELECT COUNT(*) FROM {P}").fetchone()[0]
findings["headline"]["total_rows"] = int(tot)

# ---- 1. Price-per-GPU-hour time series for marquee families ----
families = ["B200","H200","H100","A100","L40S","A10","T4"]
fig, ax = plt.subplots(figsize=(9,5))
ts_summary = {}
for i, g in enumerate(families):
    d = con.execute(f"""SELECT CAST(dt AS DATE) d, median(price_per_hour/gpu_count) p
                        {GPU} AND gpu_type='{g}' AND NOT is_spot GROUP BY 1 ORDER BY 1""").df()
    if d.empty: continue
    d["d"] = d["d"].astype("datetime64[ns]")
    # break the line wherever there is a gap > 7 days so we don't draw fake trends
    d.loc[d["d"].diff().dt.days > 7, "p"] = float("nan")
    ax.plot(d["d"], d["p"], marker="o", ms=2.5, lw=1.6, color=PALETTE[i%len(PALETTE)], label=g)
    ts_summary[g] = {"first": round(float(d["p"].iloc[0]),2), "last": round(float(d["p"].iloc[-1]),2)}
ax.axvspan(datetime.date(2026,3,9), datetime.date(2026,5,8), color="#999", alpha=0.12)
ax.text(datetime.date(2026,4,8), ax.get_ylim()[1]*0.9, "collection\ngap", ha="center", fontsize=8, color="#666")
ax.set_ylabel("Median on-demand price  ($ / GPU-hour)"); ax.set_title("On-demand price per GPU-hour by accelerator family")
ax.legend(ncol=4, fontsize=9, frameon=False); ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.0f"))
fig.autofmt_xdate()
save("01_price_timeseries")
findings["price_timeseries"] = ts_summary

# ---- 2. Generational price ladder (median $/GPU-hr, on-demand, full window) ----
ladder = con.execute(f"""SELECT gpu_type, median(price_per_hour/gpu_count) p, COUNT(*) n
    {GPU} AND NOT is_spot AND gpu_type IN ('B200','H200','H100','L40S','A100','A10','L4','V100','T4','P100','RTX4090','RTX5090','A6000')
    GROUP BY 1 ORDER BY p DESC""").df()
fig, ax = plt.subplots(figsize=(9,5))
bars = ax.barh(ladder["gpu_type"], ladder["p"], color=ACCENT)
ax.invert_yaxis()
for b,p in zip(bars, ladder["p"]):
    ax.text(b.get_width()+0.05, b.get_y()+b.get_height()/2, f"${p:.2f}", va="center", fontsize=9)
ax.set_xlabel("Median on-demand price  ($ / GPU-hour)"); ax.set_title("Generational price ladder (full sample, on-demand)")
ax.set_xlim(0, ladder["p"].max()*1.15)
save("02_generational_ladder")
findings["ladder"] = {r.gpu_type: round(float(r.p),2) for r in ladder.itertuples()}

# ---- 3. Spot savings by family ----
spot = con.execute(f"""
  WITH s AS (SELECT gpu_type, median(price_per_hour/gpu_count) sp {GPU} AND is_spot GROUP BY 1),
       o AS (SELECT gpu_type, median(price_per_hour/gpu_count) op {GPU} AND NOT is_spot GROUP BY 1)
  SELECT o.gpu_type g, o.op, s.sp, 100*(1-s.sp/o.op) disc
  FROM o JOIN s USING(gpu_type)
  WHERE o.gpu_type IN ('H100','H200','A100','L40S','A10','L4','T4','V100','RTX4090')
  ORDER BY disc DESC""").df()
fig, ax = plt.subplots(figsize=(9,5))
bars = ax.barh(spot["g"], spot["disc"], color="#059669")
ax.invert_yaxis()
for b,d in zip(bars, spot["disc"]):
    ax.text(b.get_width()+0.5, b.get_y()+b.get_height()/2, f"{d:.0f}%", va="center", fontsize=9)
ax.set_xlabel("Median spot discount vs on-demand  (%)"); ax.set_title("Spot savings by GPU family")
ax.set_xlim(0, spot["disc"].max()*1.18)
save("03_spot_savings")
findings["spot_savings"] = {r.g: {"ond": round(float(r.op),2), "spot": round(float(r.sp),2), "disc_pct": round(float(r.disc),1)} for r in spot.itertuples()}

# ---- 4. Provider price comparison for H100 (on-demand $/GPU-hr) ----
prov = con.execute(f"""SELECT provider, median(price_per_hour/gpu_count) p, COUNT(*) n
    {GPU} AND gpu_type='H100' AND NOT is_spot GROUP BY 1 HAVING COUNT(*)>50 ORDER BY p""").df()
fig, ax = plt.subplots(figsize=(9,5))
colors = ["#059669" if i==0 else ACCENT for i in range(len(prov))]
bars = ax.barh(prov["provider"], prov["p"], color=colors)
ax.invert_yaxis()
for b,p in zip(bars, prov["p"]):
    ax.text(b.get_width()+0.04, b.get_y()+b.get_height()/2, f"${p:.2f}", va="center", fontsize=9)
ax.set_xlabel("Median H100 on-demand price  ($ / GPU-hour)"); ax.set_title("H100 price spread across providers")
ax.set_xlim(0, prov["p"].max()*1.15)
save("04_provider_h100")
findings["h100_by_provider"] = {r.provider: round(float(r.p),2) for r in prov.itertuples()}
findings["h100_spread"] = {"cheapest": prov.iloc[0]["provider"], "cheapest_price": round(float(prov.iloc[0]["p"]),2),
                           "dearest": prov.iloc[-1]["provider"], "dearest_price": round(float(prov.iloc[-1]["p"]),2),
                           "ratio": round(float(prov.iloc[-1]["p"]/prov.iloc[0]["p"]),1)}

# ---- 5. Regional dispersion (H100 on-demand by region_group) ----
con.execute("CREATE TABLE regions AS SELECT * FROM read_csv_auto('data/regions.csv')")
reg = con.execute(f"""
  SELECT r.region_group rg, median(g.price_per_hour/g.gpu_count) p, COUNT(*) n
  FROM {P} g JOIN regions r ON g.provider=r.provider AND g.region=r.raw_region
  WHERE g.gpu_count>0 AND g.price_per_hour>0 AND g.gpu_type='H100' AND NOT g.is_spot AND r.region_group IS NOT NULL
  GROUP BY 1 HAVING COUNT(*)>30 ORDER BY p DESC""").df()
fig, ax = plt.subplots(figsize=(9,5))
bars = ax.barh(reg["rg"], reg["p"], color="#7c3aed")
ax.invert_yaxis()
for b,p in zip(bars, reg["p"]):
    ax.text(b.get_width()+0.03, b.get_y()+b.get_height()/2, f"${p:.2f}", va="center", fontsize=9)
ax.set_xlabel("Median H100 on-demand price  ($ / GPU-hour)"); ax.set_title("H100 price by region group")
ax.set_xlim(0, reg["p"].max()*1.15)
save("05_regional")
findings["h100_by_region"] = {r.rg: round(float(r.p),2) for r in reg.itertuples()}

# ---- 6. Market composition: listings share by provider ----
comp = con.execute(f"""SELECT provider, COUNT(*) n {GPU} GROUP BY 1 ORDER BY n DESC""").df()
top = comp.head(7).copy()
other = comp["n"][7:].sum()
labels = list(top["provider"]) + (["other"] if other>0 else [])
sizes = list(top["n"]) + ([other] if other>0 else [])
fig, ax = plt.subplots(figsize=(7,5))
ax.pie(sizes, labels=labels, autopct="%1.0f%%", colors=PALETTE+["#cbd5e1"], textprops={"fontsize":9}, pctdistance=0.8)
ax.set_title("Share of GPU listings by provider")
save("06_provider_share")
findings["provider_share"] = {str(r.provider): int(r.n) for r in comp.head(8).itertuples()}

with open("deck/findings.json","w") as f:
    json.dump(findings, f, indent=2)
print("\n=== FINDINGS ===")
print(json.dumps(findings, indent=2))
