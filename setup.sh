#!/bin/bash
# Setup script for scheduling GPUHunt price collection twice daily

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_BIN="$(which python3)"

echo "GPUHunt Price Tracker - Scheduler Setup"
echo "========================================"
echo ""
echo "This script will set up automatic price collection twice daily using gpuhunt."
echo "Installation directory: $SCRIPT_DIR"
echo "Python: $PYTHON_BIN"
echo ""

# Check if Python script exists
if [ ! -f "$SCRIPT_DIR/collect.py" ]; then
    echo "Error: collect.py not found in $SCRIPT_DIR"
    exit 1
fi

# Make scripts executable
chmod +x "$SCRIPT_DIR/collect.py"
chmod +x "$SCRIPT_DIR/report.py"
chmod +x "$SCRIPT_DIR/plot.py"

# Create data directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/data"
mkdir -p "$SCRIPT_DIR/reports"

echo "Choose scheduling method:"
echo "1) Cron (traditional, works on all systems)"
echo "2) Systemd timer (modern, systemd-based systems)"
echo "3) Manual setup (show commands only)"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "Setting up cron job for gpuhunt collection..."
        
        # Create cron job to run complete daily update at 9 AM and 9 PM
        DAILY_UPDATE_CRON="0 9,21 * * * cd $SCRIPT_DIR && $SCRIPT_DIR/daily_update.sh >> $SCRIPT_DIR/data/scheduler.log 2>&1"
        
        # Check if cron job already exists
        if crontab -l 2>/dev/null | grep -q "daily_update.sh"; then
            echo "Cron job already exists. Updating..."
            (crontab -l 2>/dev/null | grep -v "daily_update.sh" | grep -v "collect_prices_gpuhunt.py" | grep -v "report_gpuhunt.py"; echo "$DAILY_UPDATE_CRON") | crontab -
        else
            echo "Adding new cron job..."
            (crontab -l 2>/dev/null | grep -v "collect_prices_gpuhunt.py" | grep -v "report_gpuhunt.py"; echo "$DAILY_UPDATE_CRON") | crontab -
        fi
        
        echo ""
        echo "✓ Cron job installed successfully!"
        echo "  Schedule: Twice daily at 9 AM and 9 PM"
        echo "  Actions: Data collection + Reports + Plots"
        echo "  Log file: $SCRIPT_DIR/data/scheduler.log"
        echo "  Reports: $SCRIPT_DIR/reports/"
        echo "  Plots: $SCRIPT_DIR/reports/figures/"
        echo ""
        echo "To view cron jobs: crontab -l"
        echo "To remove: crontab -e (then delete the line)"
        ;;
        
    2)
        echo ""
        echo "Setting up systemd timer for gpuhunt collection..."
        
        # Create systemd service file for collection
        COLLECTION_SERVICE="/tmp/gpuhunt-collector.service"
        cat > "$COLLECTION_SERVICE" << EOF
[Unit]
Description=GPUHunt Price Collector
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_BIN $SCRIPT_DIR/collect_prices_gpuhunt.py -v
StandardOutput=append:$SCRIPT_DIR/data/gpuhunt_collection.log
StandardError=append:$SCRIPT_DIR/data/gpuhunt_collection.log
User=$USER
EOF

        # Create systemd service file for report generation
        REPORT_SERVICE="/tmp/gpuhunt-reporter.service"
        cat > "$REPORT_SERVICE" << EOF
[Unit]
Description=GPUHunt Report Generator
After=gpuhunt-collector.service

[Service]
Type=oneshot
WorkingDirectory=$SCRIPT_DIR
ExecStart=/bin/bash -c '$PYTHON_BIN $SCRIPT_DIR/report_gpuhunt.py --all > $SCRIPT_DIR/reports/gpuhunt_report_\$(date +\%Y\%m\%d_\%H\%M).txt 2>&1'
User=$USER
EOF

        # Create systemd timer file
        TIMER_FILE="/tmp/gpuhunt-collector.timer"
        cat > "$TIMER_FILE" << EOF
[Unit]
Description=GPUHunt Price Collection Timer (twice daily)

[Timer]
# Run at 9 AM and 9 PM daily
OnCalendar=*-*-* 09:00:00
OnCalendar=*-*-* 21:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

        # Create timer for report generation
        REPORT_TIMER="/tmp/gpuhunt-reporter.timer"
        cat > "$REPORT_TIMER" << EOF
[Unit]
Description=GPUHunt Report Timer
PartOf=gpuhunt-collector.timer

[Timer]
# Run 15 minutes after collection
OnCalendar=*-*-* 09:15:00
OnCalendar=*-*-* 21:15:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

        echo ""
        echo "Systemd unit files created in /tmp"
        echo ""
        echo "To install, run these commands as root:"
        echo ""
        echo "  sudo cp $COLLECTION_SERVICE /etc/systemd/system/"
        echo "  sudo cp $REPORT_SERVICE /etc/systemd/system/"
        echo "  sudo cp $TIMER_FILE /etc/systemd/system/"
        echo "  sudo cp $REPORT_TIMER /etc/systemd/system/"
        echo "  sudo systemctl daemon-reload"
        echo "  sudo systemctl enable gpuhunt-collector.timer"
        echo "  sudo systemctl enable gpuhunt-reporter.timer"
        echo "  sudo systemctl start gpuhunt-collector.timer"
        echo "  sudo systemctl start gpuhunt-reporter.timer"
        echo ""
        echo "To check status:"
        echo "  sudo systemctl status gpuhunt-collector.timer"
        echo "  sudo systemctl list-timers gpuhunt-*"
        echo ""
        
        read -p "Install now? (requires sudo) [y/N]: " install_now
        if [ "$install_now" = "y" ] || [ "$install_now" = "Y" ]; then
            sudo cp "$COLLECTION_SERVICE" /etc/systemd/system/
            sudo cp "$REPORT_SERVICE" /etc/systemd/system/
            sudo cp "$TIMER_FILE" /etc/systemd/system/
            sudo cp "$REPORT_TIMER" /etc/systemd/system/
            sudo systemctl daemon-reload
            sudo systemctl enable gpuhunt-collector.timer
            sudo systemctl enable gpuhunt-reporter.timer
            sudo systemctl start gpuhunt-collector.timer
            sudo systemctl start gpuhunt-reporter.timer
            
            echo ""
            echo "✓ Systemd timers installed and started!"
            echo ""
            sudo systemctl list-timers gpuhunt-*
        fi
        ;;
        
    3)
        echo ""
        echo "Manual Setup Instructions"
        echo "========================="
        echo ""
        echo "Cron (runs at 9 AM and 9 PM):"
        echo "  crontab -e"
        echo "  Add this line:"
        echo "  0 9,21 * * * cd $SCRIPT_DIR && $SCRIPT_DIR/daily_update.sh >> $SCRIPT_DIR/data/scheduler.log 2>&1"
        echo ""
        echo "Or run manually:"
        echo "  cd $SCRIPT_DIR"
        echo "  $PYTHON_BIN collect.py -v --stats"
        echo "  $PYTHON_BIN report.py --all"
        ;;
        
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "Setup complete!"
echo ""
echo "Test collection now:"
echo "  cd $SCRIPT_DIR"
echo "  ./gpu collect"
echo ""
echo "Generate reports:"
echo "  ./gpu report"
echo "  ./gpu best-deals H100"
echo "  ./gpu save-reports"
echo ""
echo "View outputs:"
echo "  ls -lh $SCRIPT_DIR/reports/"
echo "  ls -lh $SCRIPT_DIR/reports/figures/"
echo ""

