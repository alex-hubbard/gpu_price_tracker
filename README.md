# GPU Price Tracker

Track GPU instance prices and availability across 13+ cloud providers using the gpuhunt module. Store data in a time series database and generate reports and visualizations.

## Features

- Track 50,000+ GPU instances from 13+ providers
- Store historical pricing data in SQLite database
- Generate comprehensive reports and visualizations
- Automated twice-daily price collection
- Query historical trends

## Quick Start

### Install

```bash
pip install -r requirements.txt
```

### Collect GPU Prices

```bash
./gpu collect
```

### Generate Reports

```bash
# Display summary report
./gpu report

# Show best deals for specific GPU
./gpu best-deals H100

# Save all reports to files
./gpu save-reports
```

### Generate Visualizations

```bash
# Generate plots
./gpu plot

# View plots
ls -lh reports/figures/
```

### Set Up Automation

```bash
# Configure twice-daily collection (9 AM & 9 PM)
./gpu setup
```

## Commands

```bash
./gpu collect           # Collect GPU prices
./gpu report           # Display summary report
./gpu best-deals       # Show best deals
./gpu save-reports     # Save all reports to files
./gpu plot             # Generate visualization plots
./gpu daily-update     # Run complete update (collect + reports + plots)
./gpu setup            # Set up automated scheduler
```

## Supported Providers

- AWS, GCP, Azure
- Lambda Labs, RunPod, Vast.ai
- DataCrunch, Cudo Compute, TensorDock
- Vultr, OCI, Nebius, CloudRift

## Supported GPUs

65+ GPU types including:
- H100, H200, A100, A30, L40S, L4
- RTX 5090, RTX 4090, RTX 3090
- V100, P100, T4
- And many more

## Output Files

### Reports (text)
- `reports/report_TIMESTAMP.txt` - Comprehensive report
- `reports/best_deals_TIMESTAMP.txt` - Best deals
- `reports/best_H100_TIMESTAMP.txt` - GPU-specific reports

### Plots (PNG)
- `reports/figures/gpu_avg_prices.png` - Average price per GPU
- `reports/figures/gpu_instance_counts.png` - Instance availability
- `reports/figures/gpu_price_vs_availability.png` - Combined view

## Database

Data stored in `data/gpu_prices.db` (SQLite):
- Historical price snapshots
- Query trends over time
- Compare prices across providers

```bash
# View database stats
python3 query_history.py --stats

# Query historical trends
python3 query_history.py --trends --gpu-type H100 --days 7
```

## Documentation

- [README.md](README.md) - This file
- [methodology.md](methodology.md) - Collection methodology, schema, normalization, limitations
- [GUIDE.md](GUIDE.md) - Detailed CLI usage guide
- [MODELING_GPU_USAGE_TRENDS.md](MODELING_GPU_USAGE_TRENDS.md) - Analytical context and starter queries
- [VISUALIZATION_GUIDE.md](VISUALIZATION_GUIDE.md) - Visualization guide
- [streamlit_app/README.md](streamlit_app/README.md) - Public dashboard deploy guide

## Requirements

- Python 3.7+
- gpuhunt
- matplotlib
- tabulate
- colorama

## License

This repository is dual-licensed.

- **Code** is released under the MIT License — see [LICENSE](LICENSE).
- **Data** (the dataset published to the public S3 mirror and the
  Hugging Face Datasets repository) is released under the Creative
  Commons Attribution 4.0 International License (CC BY 4.0) — see
  [DATA_LICENSE](DATA_LICENSE).

## How to cite

If you use this dataset or software in your research, please cite it.
Citation metadata is provided in [CITATION.cff](CITATION.cff); GitHub
renders a "Cite this repository" widget from that file.

BibTeX:

```bibtex
@misc{hubbard2026gpuprices,
  author       = {Alex Hubbard},
  title        = {GPU Price Tracker},
  year         = {2026},
  howpublished = {\url{https://github.com/alex-hubbard/gpu_price_tracker}},
  note         = {Dataset and software, MIT (code) / CC BY 4.0 (data)}
}
```
