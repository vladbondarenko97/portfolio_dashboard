#!/bin/zsh

source ~/.zshrc
conda activate base
cd /Users/vladhq/Desktop/Python2026

echo "======================================"
echo "  VLADHQ CUSTOM CME DASHBOARD"
echo "======================================"

# 1. Prompt for the custom timeframe
echo -n "Enter the number of days you want to process (e.g., 7) and press [ENTER]: "
read NUM_DAYS

# If you accidentally just press enter without typing a number, default to 7
if [[ -z "$NUM_DAYS" ]]; then
    NUM_DAYS=7
fi

# 2. Generate the Custom Output Folder (e.g., Feb-22-26_7Days)
TODAY=$(date +"%b-%d-%y")
DAILY_DIR="/Users/vladhq/Desktop/CME_Data/${TODAY}_${NUM_DAYS}Days"

echo "\n▶️ STEP 1: DOWNLOADING $NUM_DAYS DAYS OF DATA..."
# We pass NUM_DAYS to the downloader so it only verifies/downloads what we need
python download_volume.py $NUM_DAYS

echo "\n▶️ STEP 2: PARSING $NUM_DAYS-DAY ARCHIVE..."
# We pass BOTH the days and the exact custom folder path to the parser
python parse_volume.py $NUM_DAYS "$DAILY_DIR"

echo "\n▶️ STEP 3: GENERATING INDICATOR CHARTS..."
# We pass the custom folder path so it reads the correct CSV and saves PNGs there
python visualize_volume.py "$DAILY_DIR"

echo "\n▶️ STEP 4: PREPARING DASHBOARD..."
cp volume_dashboard.html "$DAILY_DIR/volume_dashboard.html"

echo "\n✅ ALL STEPS COMPLETE! LAUNCHING TERMINAL..."
open "$DAILY_DIR/volume_dashboard.html"