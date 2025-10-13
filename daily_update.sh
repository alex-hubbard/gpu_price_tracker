#!/bin/bash
# Daily GPU price collection, reporting, and visualization script
# This script collects data, generates reports, and creates summary plots

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M)
LOGFILE="data/daily_update_${TIMESTAMP}.log"

# Create directories
mkdir -p data reports reports/figures

echo "========================================" | tee -a "$LOGFILE"
echo "GPU Price Tracker - Daily Update" | tee -a "$LOGFILE"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Step 1: Collect GPU prices
echo "Step 1: Collecting GPU prices from gpuhunt..." | tee -a "$LOGFILE"
python3 collect.py -v 2>&1 | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Step 2: Generate reports
echo "Step 2: Generating reports..." | tee -a "$LOGFILE"

# Comprehensive report
python3 report.py --all > "reports/report_${TIMESTAMP}.txt" 2>&1
echo "  ✓ Saved: reports/report_${TIMESTAMP}.txt" | tee -a "$LOGFILE"

# Best deals report
python3 report.py --best-deals --limit 20 > "reports/best_deals_${TIMESTAMP}.txt" 2>&1
echo "  ✓ Saved: reports/best_deals_${TIMESTAMP}.txt" | tee -a "$LOGFILE"

# GPU-specific reports
for GPU in H100 A100 L40S RTX4090 RTX5090; do
    python3 report.py --best-deals --gpu-type $GPU --limit 10 > "reports/best_${GPU}_${TIMESTAMP}.txt" 2>&1
    echo "  ✓ Saved: reports/best_${GPU}_${TIMESTAMP}.txt" | tee -a "$LOGFILE"
done

echo "" | tee -a "$LOGFILE"

# Step 3: Generate plots
echo "Step 3: Generating visualization plots..." | tee -a "$LOGFILE"
python3 plot.py --top-n 25 2>&1 | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Step 4: Database statistics
echo "Step 4: Database statistics:" | tee -a "$LOGFILE"
python3 -c "
from database import PriceDatabase
db = PriceDatabase()
stats = db.get_stats()
print(f\"  Total records: {stats['total_records']}\")
print(f\"  Snapshots: {stats['snapshots']}\")
print(f\"  Providers: {stats['providers']}\")
print(f\"  GPU types: {stats['gpu_types']}\")
print(f\"  Last snapshot: {stats['last_snapshot']}\")
" 2>&1 | tee -a "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
echo "Daily update complete!" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

echo "Generated files:" | tee -a "$LOGFILE"
echo "  Reports: reports/*_${TIMESTAMP}.txt" | tee -a "$LOGFILE"
echo "  Plots: reports/figures/*.png" | tee -a "$LOGFILE"
echo "  Log: ${LOGFILE}" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# Keep only last 30 days of logs
find data/ -name "daily_update_*.log" -mtime +30 -delete 2>/dev/null

exit 0

