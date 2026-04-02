import pandas as pd
import os
import glob
import re
from datetime import datetime
import sys

# --- CONFIGURATION ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")

# If the bash script passes a specific folder name, use it. 
if len(sys.argv) > 2:
    DAILY_DIR = sys.argv[2]
else:
    # Default fallback
    TODAY_STR = datetime.now().strftime("%b-%d-%y")
    DAILY_DIR = os.path.join(DATA_DIR, TODAY_STR)

if not os.path.exists(DAILY_DIR):
    os.makedirs(DAILY_DIR)

OUTPUT_FILE = os.path.join(DAILY_DIR, "master_market_data.csv")
# --------------------

# The exact product names as they appear in the CME Excel sheets
TARGET_PRODUCTS = [
    "E-MINI S&P 500 FUTURE",
    "MICRO E-MINI S&P 500 FUTURES",
    "SILVER FUTURES",
    "MICRO SILVER FUTURES",
    "10Y NOTE FUTURE",
    "SILVER CALL",
    "SILVER PUT",
    "E-MINI S&P 500 CALL",
    "E-MINI S&P 500 PUT"
]

def parse_cme_files(num_days=30): # <--- MAKE SURE THIS HAS num_days=30
    all_files = glob.glob(os.path.join(DATA_DIR, "daily_volume_*.xlsx"))
    all_files.sort() 
    
    # NEW: Slice the list to only include the last N days requested
    all_files = all_files[-num_days:]
    
    master_list = []
    print(f"Found {len(all_files)} files matching the {num_days}-day window. Starting extraction...")

    for file_path in all_files:
        # Extract date from filename (daily_volume_20260220.xlsx -> 2026-02-20)
        date_match = re.search(r'(\d{8})', os.path.basename(file_path))
        if not date_match: continue
        raw_date = date_match.group(1)
        formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

        print(f"Processing: {formatted_date}...")

        try:
            # Load the specific sheet. We skip the first 2 rows of headers.
            df = pd.read_excel(file_path, sheet_name='CME Group Vol and OI by Product', skiprows=2)
            
            # Clean column names (remove newlines)
            df.columns = df.columns.str.replace('\n', ' ', regex=True).str.strip()

            # Filter for our target products
            # We use isin() to get exact matches for the rows we want
            filtered_df = df[df['Product Description'].isin(TARGET_PRODUCTS)].copy()
            
            # Keep only the columns we need
            # Note: 'Open Interest ②' is the specific column name in CME files
            cols_to_keep = ['Product Description', 'Future/Option Indicator', 'Total Volume', 'Open Interest ②']
            filtered_df = filtered_df[cols_to_keep]
            
            # Add the date column
            filtered_df['Date'] = formatted_date
            
            master_list.append(filtered_df)

        except Exception as e:
            print(f"   ⚠️ Error parsing {file_path}: {e}")

    # Combine all days into one dataframe
    if not master_list:
        print("No data found!")
        return

    final_df = pd.concat(master_list)

    # --- CALCULATE DAILY OI CHANGE ---
    # We group by product and calculate the difference between today and yesterday
    print("Calculating Daily Change metrics...")
    final_df = final_df.sort_values(['Product Description', 'Date'])
    final_df['OI_Change'] = final_df.groupby('Product Description')['Open Interest ②'].diff()

    # Clean up column names for your dashboard
    final_df.columns = ['Product', 'Type', 'Volume', 'Open_Interest', 'Date', 'OI_Change']

    # Save to CSV
    final_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ SUCCESS! Master data saved to: {OUTPUT_FILE}")
    print(final_df.tail(10)) # Show preview

if __name__ == "__main__":
    days_to_run = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    parse_cme_files(days_to_run) # <--- MAKE SURE days_to_run IS INSIDE THE PARENTHESES