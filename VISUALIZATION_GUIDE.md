# Visualization Guide

Guide for generating and using GPU price visualization plots.

## Available Plots

Three types of visualization plots are generated:

### 1. Average GPU Prices (`gpu_avg_prices.png`)
- Average price per GPU for each GPU type
- Horizontal bar chart sorted by price
- Color-coded bars (green = cheaper, red = expensive)
- Shows instance count for each GPU
- Displays top 25 GPU types by instance count

### 2. GPU Instance Availability (`gpu_instance_counts.png`)
- Number of available instances per GPU type
- Horizontal bar chart sorted by instance count
- Color-coded with viridis colormap
- Shows number of providers for each GPU
- Displays top 25 GPU types

### 3. Price vs Availability (`gpu_price_vs_availability.png`)
- Scatter plot showing price and availability relationship
- Bubble size represents instance count
- Color represents price level
- Shows GPU type labels with counts
- Displays top 25 GPU types

## Quick Start

### Generate All Plots

```bash
# Using wrapper script
./gpu plot

# Or directly
python3 plot.py --top-n 25
```

### Custom Plot Generation

```bash
# Show top 30 GPU types
python3 plot.py --top-n 30

# Include "Unknown" GPU types
python3 plot.py --include-unknown

# Generate only price plot
python3 plot.py --prices-only

# Generate only instance count plot
python3 plot.py --counts-only

# Custom output directory
python3 plot.py --output-dir custom/plots/
```

## Automated Updates

### Set Up Daily Visualization

Plots are automatically generated as part of the daily update:

```bash
./gpu setup
```

This sets up a cron job that runs at 9 AM and 9 PM daily and:
1. Collects GPU prices
2. Generates reports
3. Creates visualization plots
4. Logs everything

### Manual Daily Update

Run a complete update manually:

```bash
./gpu daily-update
```

## Plot Locations

All plots are saved to:
```
reports/figures/
├── gpu_avg_prices.png
├── gpu_instance_counts.png
└── gpu_price_vs_availability.png
```

## Viewing Plots

### On Local Machine

```bash
# List plots
ls -lh reports/figures/*.png

# Open with default image viewer (Linux)
xdg-open reports/figures/gpu_avg_prices.png

# Open with default image viewer (macOS)
open reports/figures/gpu_avg_prices.png

# Windows (WSL)
explorer.exe reports/figures/gpu_avg_prices.png
```

### Copy to Accessible Location

```bash
# Copy to home directory
cp reports/figures/*.png ~/

# Copy to shared folder
cp reports/figures/*.png /mnt/c/Users/YourUsername/Desktop/
```

## Understanding the Plots

### Average GPU Prices Plot

- **X-axis**: Price per GPU per hour ($/hour)
- **Y-axis**: GPU types
- **Bar color**: Price level (green = cheap, red = expensive)
- **Text on bars**: Exact price
- **Text after bars**: Number of instances available

Example: RTX 3070 at $0.29/hr with 4 instances

### Instance Availability Plot

- **X-axis**: Number of instances
- **Y-axis**: GPU types
- **Bar color**: Relative availability
- **Text on bars**: Exact instance count
- **Text after bars**: Number of providers

Example: T4 with 1,205 instances from 3 providers

### Price vs Availability Plot

- **X-axis**: Average price per GPU ($/hour)
- **Bubble size**: Instance count
- **Color**: Price (green = cheap, red = expensive)
- **Labels**: GPU type with instance count

## Integration with Reports

Plots complement the text reports:

```bash
# 1. Collect data and generate reports
./gpu collect
./gpu save-reports

# 2. Generate visualizations
./gpu plot

# 3. Or do everything at once
./gpu daily-update
```

## Customization

### Modify Plot Parameters

Edit `plot.py` to customize:
- Figure size: Change `figsize=(14, 10)`
- Color schemes: Change `plt.cm.RdYlGn_r` or `plt.cm.viridis`
- DPI: Change `dpi=300` for higher/lower resolution
- Top N: Change default from 25

## Troubleshooting

### No Plots Generated

**Solutions:**
1. Check matplotlib is installed: `pip install matplotlib`
2. Check if data exists: `python3 query_history.py --stats`
3. Run with verbose: `python3 plot.py --top-n 25`

### Empty or Strange Plots

**Solutions:**
1. Verify database has recent data: `python3 query_history.py --snapshots --days 1`
2. Run collection first: `./gpu collect`
3. Try excluding unknown GPUs: `python3 plot.py` (unknown excluded by default)

### Plot Quality Issues

**Solutions:**
1. Increase DPI in `plot.py`: Change `dpi=600` for higher quality
2. Save as vector format (SVG) for scalability

## CLI Reference

### plot.py

```
Usage: python3 plot.py [options]

Options:
  --top-n INT          Number of top GPU types to show (default: 25)
  --include-unknown    Include "Unknown" GPU types
  --prices-only        Generate only price plot
  --counts-only        Generate only instance count plot
  --output-dir PATH    Output directory (default: reports/figures)
  -h, --help          Show help message

Examples:
  python3 plot.py --top-n 30
  python3 plot.py --include-unknown
  python3 plot.py --prices-only --output-dir custom/
```

### Wrapper Script

```
Usage: ./gpu plot

Generates 3 visualization plots:
  - Average price per GPU
  - Instance availability
  - Price vs availability scatter plot
```

## Best Practices

1. Update plots after collection:
   ```bash
   ./gpu collect
   ./gpu plot
   ```

2. Generate plots twice daily (automated via scheduler):
   ```bash
   ./gpu setup
   ```

3. Archive old plots (optional):
   ```bash
   TIMESTAMP=$(date +%Y%m%d_%H%M)
   cp reports/figures/gpu_avg_prices.png "reports/figures/archive/prices_${TIMESTAMP}.png"
   ```

4. Compare trends over time:
   ```bash
   python3 plot.py --output-dir "reports/figures/daily_$(date +%Y%m%d)"
   ```

## Workflow Examples

### Daily Morning Routine

```bash
# Check overnight price changes
./gpu daily-update

# View latest plots
xdg-open reports/figures/gpu_avg_prices.png
```

### Weekly Analysis

```bash
# Collect current data
./gpu collect

# Generate comprehensive reports
./gpu save-reports

# Create visualizations
./gpu plot

# Analyze trends
python3 query_history.py --trends --gpu-type H100 --days 7
```

### Pre-Purchase Research

```bash
# Find best deals for specific GPU
./gpu best-deals H100

# Generate visual comparison
./gpu plot

# Check price history
python3 query_history.py --trends --gpu-type H100 --days 30
```

## Files Created

When you run plot generation:

```
reports/figures/
├── gpu_avg_prices.png           (~400KB)
├── gpu_instance_counts.png      (~350KB)
└── gpu_price_vs_availability.png (~400KB)
```

## Next Steps

1. Set up automated plotting:
   ```bash
   ./gpu setup
   ```

2. Generate your first plots:
   ```bash
   ./gpu plot
   ```

3. View the plots:
   ```bash
   ls -lh reports/figures/
   xdg-open reports/figures/gpu_avg_prices.png
   ```

4. Integrate with your workflow:
   ```bash
   ./gpu daily-update
   ```

## See Also

- [README.md](README.md) - Project overview
- [GUIDE.md](GUIDE.md) - Complete usage guide
