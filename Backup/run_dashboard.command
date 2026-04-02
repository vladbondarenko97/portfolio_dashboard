#!/bin/zsh

# 1. Load your standard terminal profile so it recognizes the 'conda' command
source ~/.zshrc

# 2. Activate your environment
conda activate base

# 3. Navigate to your working directory
cd /Users/vladhq/Desktop/Python2026

# Generate today's date folder string (e.g., Feb-22-26)
TODAY=$(date +"%b-%d-%y")
DAILY_DIR="/Users/vladhq/Desktop/CME_Data/$TODAY"

echo "======================================"
echo "  VLADHQ CME DASHBOARD AUTO-UPDATER"
echo "  Target Run Folder: $TODAY"
echo "======================================"

echo "\n▶️ STEP 1: DOWNLOADING LATEST CME DATA..."
python download_volume_30days.py

echo "\n▶️ STEP 2: PARSING 30-DAY ARCHIVE..."
python parse_volume_30days.py

echo "\n▶️ STEP 3: GENERATING INDICATOR CHARTS..."
python visualize_volume.py

echo "\n▶️ STEP 4: PREPARING DASHBOARD..."
# Copy the master HTML template into today's specific folder
cp volume_dashboard.html "$DAILY_DIR/volume_dashboard.html"

echo "\n✅ ALL STEPS COMPLETE! LAUNCHING TERMINAL..."
# Open today's specific dashboard
open "$DAILY_DIR/volume_dashboard.html"