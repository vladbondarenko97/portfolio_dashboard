#!/bin/zsh
set -e

source ~/.zshrc
conda activate base
cd "$(dirname "$0")"

# Generate today's unified execution folder
TODAY=$(date +"%b-%d-%y")
DAILY_DIR="../CME_Data/$TODAY"

echo "======================================"
echo "  VLADHQ DUAL-HORIZON DASHBOARD"
echo "  Target Run Folder: $TODAY"
echo "======================================"

echo "\n▶️ Launching Background Tasks (Scanners & Email)..."
python send_email.py &
python institutional_scanner.py &

echo "\n▶️ Launching Foreground Task (In-Memory CME Pipeline)..."
python main_pipeline.py

# Wait for background tasks to finish
echo "\n⏳ Waiting for background tasks to finish..."
wait

echo "\n✅ ALL STEPS COMPLETE! LAUNCHING DASHBOARD..."
open "$DAILY_DIR/volume_dashboard.html"