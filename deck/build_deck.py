#!/usr/bin/env python3
"""Build a self-contained HTML slide deck (base64-embedded figures, no external deps)."""
import json, base64, pathlib, html

F = json.load(open("deck/findings.json"))
h = F["headline"]
def b64(name):
    return base64.b64encode(open(f"deck/figures/{name}.png","rb").read()).decode()

def img(name):
    return f'<img class="chart" src="data:image/png;base64,{b64(name)}"/>'

hp = F["h100_spread"]
spot = F["spot_savings"]
ladder = F["ladder"]
G = json.load(open("deck/geo_findings.json"))
hubs = G["top_hubs"]; conc = G["concentration"]; fp = G["footprints"]

slides = []

slides.append(f"""
<section class="title">
  <div class="kicker">Market analysis · Jan – Jun 2026</div>
  <h1>The GPU Rental Market,<br>Priced by the Hour</h1>
  <p class="sub">What {h['gpu_listings']:,} cloud GPU listings across {h['providers']} providers reveal about
  accelerator pricing, spot economics, and where capacity is tight.</p>
  <div class="byline">GPU Price Tracker · {h['start']} → {h['end']}</div>
</section>""")

slides.append(f"""
<section>
  <h2>The dataset at a glance</h2>
  <div class="stats">
    <div class="stat"><div class="num">{h['gpu_listings']/1e3:.0f}K</div><div class="lbl">GPU listings observed</div></div>
    <div class="stat"><div class="num">{h['providers']}</div><div class="lbl">cloud providers</div></div>
    <div class="stat"><div class="num">{h['gpu_types']}</div><div class="lbl">distinct GPU types</div></div>
    <div class="stat"><div class="num">{h['days']}</div><div class="lbl">snapshot days</div></div>
  </div>
  <ul>
    <li>One row per <b>cloud listing</b>, scraped twice daily via <code>gpuhunt</code> — an unbalanced panel keyed on
        <code>(timestamp, provider, instance&nbsp;type, region, spot)</code>.</li>
    <li>Spans hyperscalers (AWS, GCP, Azure, OCI) and GPU marketplaces (Lambda, RunPod, Vast.ai, DataCrunch, …).</li>
    <li>Covers legacy (T4, V100, P100) through current data-center silicon (H100, H200, <b>B200</b>) side by side.</li>
  </ul>
</section>""")

slides.append(f"""
<section>
  <h2>We price the market — not the meter</h2>
  <p class="lead">Nothing here measures GPU-hours actually consumed. Two observable proxies move with demand:</p>
  <div class="cols">
    <div class="card">
      <h3>① Price signal</h3>
      <p>Spot prices on marketplaces are an instantaneous clearing signal for supply–demand imbalance.
      On-demand list prices move slowly and reflect <i>posted</i>, not cleared, pricing.</p>
    </div>
    <div class="card">
      <h3>② Inventory signal</h3>
      <p>The count of offered instances per <code>(gpu, provider, region)</code> tracks exposed capacity.
      Marketplaces list only free inventory — its complement is a usage proxy.</p>
    </div>
  </div>
  <p class="note">Read the data as a <b>market-microstructure view</b> of GPU rental — strongest on marketplaces,
  weakest on hyperscalers whose list prices are sticky.</p>
</section>""")

slides.append(f"""
<section>
  <h2>A 17× price ladder, top to bottom</h2>
  {img("02_generational_ladder")}
  <p class="caption">Median on-demand <b>$/GPU-hour</b> across the full sample. Frontier silicon (B200 ≈ ${ladder['B200']:.2f},
  H100 ≈ ${ladder['H100']:.2f}) commands a steep premium over consumer cards (RTX&nbsp;4090 ≈ ${ladder['RTX4090']:.2f}) —
  the spread buyers navigate when choosing price vs. performance.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Prices are sticky — until they aren't</h2>
  {img("01_price_timeseries")}
  <p class="caption">Two collection epochs bracket a 60-day scraper outage (shaded — lines intentionally broken, not interpolated).
  Most families are flat to mildly rising; <b>H200</b> roughly doubled between epochs as scarce frontier supply re-priced.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Spot is the real discount lever</h2>
  {img("03_spot_savings")}
  <p class="caption">Median spot discount vs. on-demand. Commodity GPUs (T4, A10) shed ~70%+ on spot, while
  frontier H100/H200 hold the line at ~45–49% — scarce silicon is rarely idle, so its spot discount compresses.</p>
</section>""")

slides.append(f"""
<section>
  <h2>The same H100 costs {hp['ratio']}× more — depending who you ask</h2>
  {img("04_provider_h100")}
  <p class="caption">Median H100 on-demand $/GPU-hour. Marketplaces (<b>{hp['cheapest']}</b> ≈ ${hp['cheapest_price']:.2f})
  undercut hyperscalers (<b>{hp['dearest']}</b> ≈ ${hp['dearest_price']:.2f}) by a factor of {hp['ratio']}× —
  the single largest cost lever in the dataset, dwarfing GPU choice or region.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Geography is a price tier too</h2>
  {img("05_regional")}
  <p class="caption">Median H100 on-demand $/GPU-hour by region group (geocoded via the regions table). Core
  North-American and Northern-European regions are cheapest; thin emerging-market regions carry a scarcity premium.</p>
</section>""")

# ---- US geographic block ----
slides.append(f"""
<section>
  <h2>Mapping US GPU supply</h2>
  {img("07_us_supply_map")}
  <p class="caption">Every geocoded US listing, clustered by metro. <b>{hubs[0]['metro']}</b> ({hubs[0]['listings']//1000}K listings,
  the widest GPU catalog) anchors the east; <b>{hubs[1]['metro']}</b> and <b>{hubs[2]['metro']}</b> lead the center and west.
  The top three metros hold <b>{conc['top3_share_pct']:.0f}%</b> of all US GPU listings across {conc['n_metros']} metros — supply is highly concentrated.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Where each GPU lives</h2>
  {img("08_gpu_metro_heatmap")}
  <p class="caption">Listings by GPU family × metro (log color). Legacy inference parts (T4, V100) blanket the major hubs;
  scarce frontier <b>B200</b> is thin and scattered (tens–hundreds per site). Virginia and Iowa carry the deepest, broadest inventory.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Footprint widens as silicon matures</h2>
  {img("09_gpu_footprints")}
  <p class="caption">Newer accelerators start concentrated and spread out as supply scales:
  <b>B200</b> reaches {fp['B200']['sites']} metros ({fp['B200']['listings']:,} listings),
  <b>H100</b> {fp['H100']['sites']}, <b>A100</b> {fp['A100']['sites']}, and commodity
  <b>T4</b> blankets {fp['T4']['sites']} metros ({fp['T4']['listings']:,} listings) — the clearest geographic read on the adoption curve.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Coverage is concentrated in the hyperscalers</h2>
  {img("06_provider_share")}
  <p class="caption">Share of GPU listings by provider. The big-three hyperscalers dominate <i>listing volume</i> —
  but contribute the least <i>price signal</i>, since their on-demand prices barely move. Marketplaces punch above
  their weight analytically.</p>
</section>""")

slides.append(f"""
<section>
  <h2>Know the limits before you model</h2>
  <div class="cols">
    <ul>
      <li><b>No customer telemetry.</b> Rented hours, concurrency, utilization are never observed — all "usage" is inferred.</li>
      <li><b>On-demand is sticky.</b> Hyperscaler list prices can sit constant for weeks; lean on marketplace spot for demand signal.</li>
      <li><b>Listing counts ≠ capacity.</b> A drop can be a delist <i>or</i> a scraper miss — always check provider coverage first.</li>
    </ul>
    <ul>
      <li><b>Mind the gap.</b> A 60-day outage splits the series into two epochs — never interpolate across it.</li>
      <li><b>12-hour cadence is coarse.</b> Intraday auction dynamics are smoothed away.</li>
      <li><b>Regions need geocoding.</b> Cross-provider comparison relies on a mapping layer, not raw region strings.</li>
    </ul>
  </div>
</section>""")

slides.append(f"""
<section>
  <h2>From prices to a usage model</h2>
  <p class="lead">The dataset is positioned for these modeling questions:</p>
  <div class="cols">
    <div class="card"><h3>Tightness index</h3><p>Spot–on-demand spread per family — the most defensible single
    "usage pressure" signal, robust to listing noise.</p></div>
    <div class="card"><h3>Price forecasting</h3><p>Short-horizon ARIMA / gradient-boosted models with lag, spread,
    and time-of-day features, hierarchical across GPU families.</p></div>
    <div class="card"><h3>Change-point detection</h3><p>Flag launches, capacity expansions, and export-control shocks
    as regime shifts — no labels required.</p></div>
  </div>
  <p class="note">Strengthen it with: a launch-date event timeline, public demand proxies (HF/PyPI downloads),
  and higher-frequency spot snapshots on marketplaces.</p>
</section>""")

slides.append(f"""
<section class="title closing">
  <div class="kicker">Takeaways</div>
  <h1>Three numbers to remember</h1>
  <div class="stats">
    <div class="stat"><div class="num">{hp['ratio']}×</div><div class="lbl">H100 price gap,<br>marketplace vs hyperscaler</div></div>
    <div class="stat"><div class="num">~45%</div><div class="lbl">spot discount even on<br>scarce frontier H100</div></div>
    <div class="stat"><div class="num">17×</div><div class="lbl">spread top-to-bottom<br>of the GPU ladder</div></div>
  </div>
  <p class="sub">Where you buy beats what you buy. The cheapest lever is provider choice — then spot, then GPU generation.</p>
</section>""")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b1020;--card:#141b2e;--ink:#e7ecf5;--mut:#9aa7c0;--accent:#3b82f6;--accent2:#22d3ee}
html,body{height:100%}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;overflow:hidden}
.deck{height:100vh;width:100vw}
section{display:none;height:100vh;width:100vw;padding:5vh 7vw;flex-direction:column;justify-content:center}
section.active{display:flex}
h1{font-size:clamp(34px,5.2vw,68px);line-height:1.05;font-weight:800;letter-spacing:-1.5px}
h2{font-size:clamp(26px,3.4vw,44px);font-weight:750;letter-spacing:-1px;margin-bottom:2.2vh;color:#fff}
h3{font-size:clamp(16px,1.5vw,21px);color:var(--accent2);margin-bottom:8px}
p{font-size:clamp(15px,1.5vw,21px);line-height:1.5;color:var(--ink)}
ul{list-style:none;margin:1vh 0}
li{font-size:clamp(14px,1.45vw,20px);line-height:1.45;color:var(--ink);padding:7px 0 7px 26px;position:relative}
li:before{content:"";position:absolute;left:0;top:15px;width:9px;height:9px;border-radius:2px;background:var(--accent)}
b{color:#fff;font-weight:700}
code{background:#1e2740;color:var(--accent2);padding:1px 6px;border-radius:5px;font-size:0.88em}
.kicker{color:var(--accent2);font-weight:700;letter-spacing:2px;text-transform:uppercase;font-size:clamp(12px,1.2vw,15px);margin-bottom:2.2vh}
.title{align-items:flex-start}
.title .sub{color:var(--mut);max-width:60ch;margin-top:3vh;font-size:clamp(16px,1.7vw,24px)}
.byline{margin-top:5vh;color:var(--mut);font-size:15px;border-top:1px solid #243049;padding-top:18px}
.lead{color:var(--mut);margin-bottom:2vh}
.note{margin-top:2vh;color:var(--mut);border-left:3px solid var(--accent);padding-left:16px}
.caption{margin-top:1.6vh;color:var(--mut);font-size:clamp(13px,1.35vw,18px);max-width:95ch}
img.chart{max-height:62vh;max-width:100%;align-self:center;background:#fff;border-radius:10px;padding:10px;box-shadow:0 16px 50px rgba(0,0,0,.45)}
.stats{display:flex;gap:3vw;margin:3vh 0;flex-wrap:wrap}
.stat{flex:1;min-width:150px}
.stat .num{font-size:clamp(40px,6vw,86px);font-weight:850;color:var(--accent2);letter-spacing:-2px;line-height:1}
.stat .lbl{color:var(--mut);font-size:clamp(13px,1.3vw,18px);margin-top:8px}
.cols{display:flex;gap:2.5vw;margin:1vh 0}
.cols>*{flex:1}
.card{background:var(--card);border:1px solid #243049;border-radius:14px;padding:22px 24px}
.card p{color:var(--mut);font-size:clamp(14px,1.35vw,18px)}
.closing .sub{color:var(--mut);max-width:70ch;margin-top:1vh}
.nav{position:fixed;bottom:18px;right:26px;color:var(--mut);font-size:13px;z-index:10;user-select:none}
.bar{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--accent2));z-index:10;transition:width .25s}
"""

JS = """
const s=[...document.querySelectorAll('section')];let i=0;
const bar=document.querySelector('.bar'),nav=document.querySelector('.nav');
function show(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach((x,k)=>x.classList.toggle('active',k===i));
bar.style.width=((i+1)/s.length*100)+'%';nav.textContent=(i+1)+' / '+s.length;}
document.addEventListener('keydown',e=>{
 if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key)){show(i+1);e.preventDefault();}
 else if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){show(i-1);e.preventDefault();}
 else if(e.key==='Home')show(0);else if(e.key==='End')show(s.length-1);
 else if(e.key==='f'){if(!document.fullscreenElement)document.documentElement.requestFullscreen();else document.exitFullscreen();}});
document.addEventListener('click',e=>{if(e.clientX>window.innerWidth*0.5)show(i+1);else show(i-1);});
show(0);
"""

doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU Rental Market — Jan–Jun 2026</title><style>{CSS}</style></head>
<body><div class="bar"></div><div class="deck">{''.join(slides)}</div>
<div class="nav"></div><script>{JS}</script></body></html>"""

pathlib.Path("deck/gpu_market_deck.html").write_text(doc)
print(f"wrote deck/gpu_market_deck.html ({len(doc)//1024} KB, {len(slides)} slides)")
