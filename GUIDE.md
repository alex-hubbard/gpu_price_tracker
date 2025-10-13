# GPU Price Tracker Guide

Complete guide for using the GPU price tracker powered by gpuhunt.

## Overview

Track GPU prices from 13+ cloud providers including AWS, GCP, Azure, Lambda Labs, RunPod, Vast.ai, DataCrunch, and more. The system collects pricing data, stores it in a time series database, and generates reports and visualizations.

## Installation

```bash
pip install -r requirements.txt
```

## Basic Usage

### Collect Prices

```bash
# Collect all GPU prices
./gpu collect

# Or use Python directly
python3 collect.py -v --stats
```

### Generate Reports

```bash
# Display summary report
./gpu report

# Show best deals
./gpu best-deals

# Show best deals for specific GPU
./gpu best-deals H100

# Save all reports to files
./gpu save-reports
```

### Generate Plots

```bash
# Generate visualization plots
./gpu plot

# View generated plots
ls -lh reports/figures/
```

### Complete Update

```bash
# Run complete update (collect + reports + plots)
./gpu daily-update
```

## Automated Collection

### Setup

```bash
./gpu setup
```

Choose from:
1. Cron (recommended) - Runs at 9 AM and 9 PM daily
2. Systemd timer - For systemd-based systems
3. Manual setup - View commands only

### What Gets Automated

The scheduler will:
1. Collect GPU prices (50,000+ instances)
2. Store data in time series database
3. Generate text reports
4. Create visualization plots
5. Log everything to `data/scheduler.log`

### View Scheduled Jobs

```bash
# View cron jobs
crontab -l

# View systemd timers (if using systemd)
sudo systemctl list-timers
```

## Reports

### Text Reports

Saved to `reports/`:
- `report_TIMESTAMP.txt` - Comprehensive report
- `best_deals_TIMESTAMP.txt` - Best deals overall
- `best_H100_TIMESTAMP.txt` - GPU-specific reports
- `best_A100_TIMESTAMP.txt`
- `best_L40S_TIMESTAMP.txt`
- `best_RTX4090_TIMESTAMP.txt`

### Visualization Plots

Saved to `reports/figures/`:
- `gpu_avg_prices.png` - Average price per GPU
- `gpu_instance_counts.png` - Instance availability by GPU
- `gpu_price_vs_availability.png` - Combined scatter plot

## Database Queries

### View Statistics

```bash
python3 query_history.py --stats
```

### View Snapshots

```bash
# Last 7 days
python3 query_history.py --snapshots --days 7

# Last 30 days
python3 query_history.py --snapshots --days 30
```

### Query Trends

```bash
# Price trends for H100
python3 query_history.py --trends --gpu-type H100 --days 7

# Price trends for A100 from specific provider
python3 query_history.py --trends --gpu-type A100 --provider vastai --days 30
```

## Collection Options

### Filter by GPU

```bash
python3 collect.py --gpu-name H100 -v
python3 collect.py --gpu-name A100 -v
```

### Filter by Specs

```bash
# Minimum 80GB GPU memory
python3 collect.py --min-gpu-memory 80 -v

# Minimum 16 CPUs
python3 collect.py --min-cpu 16 -v

# Maximum $5/hour
python3 collect.py --max-price 5.0 -v
```

### Filter by Provider

```bash
python3 collect.py --provider aws -v
python3 collect.py --provider vastai -v
```

## Report Options

### Summary Report

```bash
python3 report.py --summary
python3 report.py --summary -v  # Verbose
```

### Best Deals

```bash
# Overall best deals
python3 report.py --best-deals --limit 20

# GPU-specific deals
python3 report.py --best-deals --gpu-type H100 --limit 10
```

### Provider Comparison

```bash
python3 report.py --providers
```

### Availability by Region

```bash
python3 report.py --availability
```

### All Reports

```bash
python3 report.py --all -v
```

## Visualization Options

### Generate Plots

```bash
# Default: top 25 GPUs
python3 plot.py --top-n 25

# Top 30 GPUs
python3 plot.py --top-n 30

# Include "Unknown" GPU types
python3 plot.py --include-unknown
```

### Generate Specific Plots Only

```bash
# Price plot only
python3 plot.py --prices-only

# Instance count plot only
python3 plot.py --counts-only
```

### Custom Output Directory

```bash
python3 plot.py --output-dir custom/plots/
```

## Supported Providers

- AWS - Amazon Web Services
- GCP - Google Cloud Platform
- Azure - Microsoft Azure
- Lambda Labs - Specialized GPU cloud
- RunPod - GPU cloud platform
- Vast.ai - Peer-to-peer GPU marketplace
- DataCrunch - AI/ML cloud provider
- Cudo Compute - Distributed cloud
- TensorDock - GPU cloud provider
- Vultr - Cloud hosting
- OCI - Oracle Cloud Infrastructure
- Nebius - Cloud provider
- CloudRift - GPU cloud

## Supported GPU Types

### High-End AI/Training
- H200, H100, A100, A30
- MI300X (AMD)
- TPU v5p, v6e (Google)

### Mid-Range
- L40S, L40, L4, A40, A10, A10G
- RTX 6000 Ada, RTX 5000 Ada, RTX A6000

### Consumer/Gaming
- RTX 5090, 5080, 5070 Ti, 5070
- RTX 4090, 4080 Super, 4070 Ti
- RTX 3090, 3080 Ti, 3070

### Legacy
- V100, P100, T4

## Troubleshooting

### No Data Collected

```bash
# Check internet connection
ping google.com

# Verify gpuhunt is installed
pip list | grep gpuhunt

# Run with verbose output
python3 collect.py -v
```

### Database Errors

```bash
# Check database stats
python3 query_history.py --stats

# Verify database file exists
ls -lh data/gpu_prices.db
```

### Reports Empty

```bash
# Ensure data has been collected
python3 query_history.py --stats

# Run complete update
./gpu daily-update
```

### Plots Not Generated

```bash
# Check matplotlib is installed
pip list | grep matplotlib

# Verify data exists
python3 query_history.py --stats

# Run plot generation
python3 plot.py --top-n 25
```

## Best Practices

1. Run collection twice daily for accurate trends
2. Save reports to track changes over time
3. Use filters when looking for specific GPUs
4. Check logs regularly: `tail -f data/scheduler.log`
5. Compare prices across providers using best-deals report

## Examples

### Find Cheapest H100

```bash
./gpu best-deals H100
```

### Track H100 Price Over Week

```bash
# Collect data twice daily for a week (automated)
./gpu setup

# After a week, query trends
python3 query_history.py --trends --gpu-type H100 --days 7
```

### Compare All A100 Prices

```bash
python3 report.py --summary -v | grep -A 5 "A100"
```

### Generate Daily Report

```bash
./gpu daily-update
cat reports/report_$(date +%Y%m%d)*.txt
```

## Files and Directories

```
gpu_price_tracker/
├── collect.py          # Data collection
├── report.py           # Report generation
├── plot.py             # Visualization
├── query_history.py    # Historical queries
├── database.py         # Database operations
├── models.py           # Data models
├── gpu                 # Main CLI wrapper
├── setup.sh            # Scheduler setup
├── daily_update.sh     # Complete daily update
├── generate_reports.sh # Report generation
├── data/               # Database and logs
├── reports/            # Text reports
└── reports/figures/    # Visualization plots
```

## CLI Reference

### collect.py

```
Options:
  -v, --verbose          Verbose output
  --stats                Show database statistics
  --min-gpu-memory INT   Minimum GPU memory in GB
  --min-cpu INT          Minimum CPUs
  --max-price FLOAT      Maximum price per hour
  --gpu-name TEXT        Filter by GPU name
  --provider TEXT        Filter by provider
```

### report.py

```
Options:
  --summary              Summary report (default)
  --providers            Provider-based report
  --best-deals           Best deals
  --availability         Availability by region
  --all                  All reports
  --gpu-type TEXT        Filter by GPU type
  --limit INT            Limit results (default: 10)
  -v, --verbose          Verbose output
```

### plot.py

```
Options:
  --top-n INT            Number of GPU types to show (default: 25)
  --include-unknown      Include "Unknown" GPU types
  --prices-only          Generate price plot only
  --counts-only          Generate instance count plot only
  --output-dir PATH      Output directory (default: reports/figures)
```

### gpu (wrapper script)

```
Commands:
  collect         Collect GPU prices
  report          Display summary report
  best-deals      Show best deals
  save-reports    Save all reports to files
  plot            Generate visualization plots
  daily-update    Run complete update
  setup           Set up automated scheduler
```

## License

MIT
