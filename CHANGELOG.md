# Changelog

## 2026-07-08 - Dataset schema v1.1 & public release polish

### Summary
Prepared the repository and dataset for public sharing: schema v1.1
(quality tags + region enrichment), a uniform backfill of all published
snapshots, a rewritten README, and CI now fully owns the twice-daily
cadence.

### Added
- `quality` column, tagged at collection time (`ok` / `unknown_gpu` /
  `missing_memory`); CPU-only SKUs (`gpu_count = 0`) are now dropped at
  the source and appear only in historical snapshots as `cpu_only`
- Region enrichment columns in the published Parquet
  (`region_canonical`, `country`, `region_lat`, `region_lon`,
  `region_group`) joined from `data/regions.csv`
- Parquet file-level provenance metadata (`schema_version`, `row_count`,
  `quality_summary`, `git_sha`, `gpuhunt_version`)
- `scripts/upgrade_parquet_schema.py` — in-place upgrade of pre-v1.1
  snapshot files; the whole published tree is now schema-uniform
- Second CI cron (21:00 UTC) so the twice-daily cadence no longer
  depends on a local machine

### Changed
- README rewritten around dataset access (Hugging Face, DuckDB, S3);
  live dashboard at https://gpu-price-trends.streamlit.app/
- Dashboard query layer reads Parquet with `union_by_name` and coalesces
  quality/region columns, so mixed-vintage snapshot trees stay queryable
- Schema docs (`methodology.md`, `dataset_card.md`) updated for v1.1
- `.gitignore`: logs, the SQLite db, generated reports, and analysis
  notebooks are no longer trackable by accident

## 2025-10-13 - Repository Simplification

### Summary
Cleaned up repository to use only gpuhunt module. Removed old AWS/GCP/Azure system and simplified structure.

### Added
- Simplified README with no emojis
- Consolidated GUIDE.md (replaced GPUHUNT_GUIDE.md)
- Simplified VISUALIZATION_GUIDE.md with no emojis

### Changed
- Renamed `collect_prices_gpuhunt.py` → `collect.py`
- Renamed `report_gpuhunt.py` → `report.py`
- Renamed `plot_gpu_summary.py` → `plot.py`
- Renamed `setup_gpuhunt_scheduler.sh` → `setup.sh`
- Renamed `gpuhunt.sh` → `gpu`
- Simplified `requirements.txt` to 4 packages only
- Updated all scripts to use new filenames
- Removed all emojis from documentation

### Removed
- `main.py` - Old interactive CLI
- `collect_prices.py` - Old AWS/GCP/Azure collector
- `cache.py` - Not needed with gpuhunt
- `visualize.py` - Old time series visualization
- `setup_scheduler.sh` - Old scheduler
- `test_dynamic_discovery.py` - Test file
- `providers/` - Old provider modules
- `gpu_price_tracker/` - Old package
- `docs/`, `notebooks/`, `references/`, `models/` - Development directories
- `pyproject.toml`, `Makefile` - Build files
- `EXAMPLES.md` - Redundant documentation
- `DYNAMIC_FETCHING.md` - Old system documentation
- `PROJECT_SUMMARY.md` - Redundant documentation
- `QUICK_START.md` - Redundant documentation
- `SCHEDULER_GUIDE.md` - Redundant documentation
- `GPUHUNT_IMPLEMENTATION.md` - Technical documentation
- `COMPLETE_SYSTEM_SUMMARY.md` - Redundant documentation

### Final Structure

**Core Scripts (10 files):**
- `collect.py` - Data collection using gpuhunt
- `report.py` - Report generation
- `plot.py` - Visualization plots
- `query_history.py` - Query historical data
- `database.py` - Database operations
- `models.py` - Data models
- `gpu` - CLI wrapper
- `setup.sh` - Scheduler setup
- `daily_update.sh` - Complete daily update
- `generate_reports.sh` - Report generation

**Documentation (3 files):**
- `README.md` - Project overview
- `GUIDE.md` - Complete usage guide
- `VISUALIZATION_GUIDE.md` - Visualization guide

**Dependencies:**
- `requirements.txt` - 4 packages (gpuhunt, matplotlib, tabulate, colorama)

### Usage

Simple CLI commands:
```bash
./gpu collect        # Collect GPU prices
./gpu report         # Display summary report
./gpu best-deals H100 # Show H100 best deals
./gpu save-reports   # Save all reports
./gpu plot           # Generate visualization plots
./gpu daily-update   # Complete update
./gpu setup          # Set up automation
```

### Database
- 25,032 price records maintained
- 2 snapshots preserved
- 13 providers tracked
- 65 GPU types monitored
- All historical data intact

