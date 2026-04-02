#!/bin/zsh

source ~/.zshrc
conda activate base
cd /Users/vladhq/Desktop/Python2026

# Generate today's unified execution folder
TODAY=$(date +"%b-%d-%y")
DAILY_DIR="/Users/vladhq/Desktop/CME_Data/$TODAY"

echo "======================================"
echo "  VLADHQ DUAL-HORIZON DASHBOARD"
echo "  Target Run Folder: $TODAY"
echo "======================================"

echo "\n▶️ STEP 1: DOWNLOADING LATEST CME DATA (30 DAYS)..."
# We revert to pulling the standard 30-day block, no sys args needed
#python download_volume.py

echo "\n▶️ STEP 1.5: PULLING PHYSICAL COMEX INVENTORY..."
python update_inventory.py

echo "\n▶️ STEP 2: PARSING MASTER ARCHIVE..."
# Parse the full 30 days
python parse_volume.py 30 "$DAILY_DIR"

echo "\n▶️ STEP 3: GENERAING TACTICAL RULING (MACRO SNAPSHOT)..."
python tactical_ruling.py > "$DAILY_DIR/tactical_ruling.txt"

echo "\n▶️ STEP 4: GENERATING DUAL-HORIZON CHARTS..."
# The visualizer will now slice and save both 30d and 7d charts automatically
python visualize_volume.py "$DAILY_DIR"

echo "\n▶️ STEP 5: GENERATING TEXT DATA DUMP..."
python dump_data.py 

echo "\n▶️ STEP 6: Synthesizing data & generating an e-mail report..."
python send_email.py  # runs market_reader.py & options_scanner.py

echo "\n✅ ALL STEPS COMPLETE! LAUNCHING TERMINAL..."
open "$DAILY_DIR/volume_dashboard.html"