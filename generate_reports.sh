#!/bin/bash
# Generate and save GPU pricing reports

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create reports directory if it doesn't exist
mkdir -p reports

# Generate timestamp for filenames
TIMESTAMP=$(date +%Y%m%d_%H%M)

echo "Generating GPU pricing reports..."
echo "Timestamp: $TIMESTAMP"
echo ""

# Generate comprehensive report
echo "1. Generating comprehensive report..."
python3 report.py --all > "reports/report_${TIMESTAMP}.txt" 2>&1
echo "   ✓ Saved to: reports/report_${TIMESTAMP}.txt"

# Generate best deals report
echo "2. Generating best deals report..."
python3 report.py --best-deals --limit 20 > "reports/best_deals_${TIMESTAMP}.txt" 2>&1
echo "   ✓ Saved to: reports/best_deals_${TIMESTAMP}.txt"

# Generate GPU-specific reports for popular types
for GPU in H100 A100 L40S RTX4090; do
    echo "3. Generating $GPU best deals..."
    python3 report.py --best-deals --gpu-type $GPU --limit 10 > "reports/best_${GPU}_${TIMESTAMP}.txt" 2>&1
    echo "   ✓ Saved to: reports/best_${GPU}_${TIMESTAMP}.txt"
done

echo ""
echo "4. Generating summary plots..."
python3 plot.py --top-n 25 2>/dev/null
echo "   ✓ Saved plots to: reports/figures/"

echo ""
echo "All reports and plots generated!"
echo ""
echo "View reports:"
echo "  ls -lh reports/*.txt"
echo ""
echo "View plots:"
echo "  ls -lh reports/figures/*.png"
echo ""
echo "Read a report:"
echo "  cat reports/report_${TIMESTAMP}.txt"
echo "  cat reports/best_deals_${TIMESTAMP}.txt"
echo ""

