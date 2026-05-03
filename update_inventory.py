import os
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright
import warnings

# Suppress styling warnings from CME's Excel files
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# --- CONFIGURATION ---
from config import DATA_DIR
URL = "https://www.cmegroup.com/delivery_reports/Silver_stocks.xls"
HISTORY_FILE = os.path.join(DATA_DIR, "comex_inventory_history.csv")

def update_silver_inventory():
    print("▶️ Downloading latest COMEX Silver Inventory...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    raw_save_path = os.path.join(DATA_DIR, f"silver_stocks_{today_str}.xls")

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--disable-http2'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            accept_downloads=True
        )
        page = context.new_page()
        try:
            with page.expect_download(timeout=30000) as download_info:
                try: page.goto(URL)
                except Exception as e:
                    if "Download is starting" not in str(e): raise e
            download = download_info.value
            download.save_as(raw_save_path)
            print(f"✅ Downloaded to: {raw_save_path}")
        except Exception as e:
            print(f"❌ Failed to download: {e}")
            browser.close()
            return
        browser.close()

    print(f"▶️ Parsing {raw_save_path}...")
    try:
        # Load the file - skipping headers to reach the data table
        df = pd.read_excel(raw_save_path, skiprows=7)
        
        # Clean labels in the first column for searching
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.strip().str.upper()
        labels = df.iloc[:, 0]
        
        # Search for the Grand Total labels at the bottom of the report
        reg_row = df[labels == "TOTAL REGISTERED"]
        elig_row = df[labels == "TOTAL ELIGIBLE"]
        comb_row = df[labels == "COMBINED TOTAL"]
        
        if not reg_row.empty and not elig_row.empty:
            # Index 5 is NET CHANGE, Index 7 is TOTAL TODAY
            registered = float(str(reg_row.iloc[0, 7]).replace(',', ''))
            reg_change = float(str(reg_row.iloc[0, 5]).replace(',', ''))
            
            eligible = float(str(elig_row.iloc[0, 7]).replace(',', ''))
            elig_change = float(str(elig_row.iloc[0, 5]).replace(',', ''))
            
            total_today = float(str(comb_row.iloc[0, 7]).replace(',', ''))
            total_change = float(str(comb_row.iloc[0, 5]).replace(',', ''))
            
            # FIXED FORMATTING: Added the period before '0f'
            print(f"📊 Extracted -> Registered: {registered:,.0f} ({reg_change:+,.0f})")
            print(f"📊 Extracted -> Eligible:   {eligible:,.0f} ({elig_change:+,.0f})")
            print(f"📊 Extracted -> Combined:   {total_today:,.0f} ({total_change:+,.0f})")

            new_entry = pd.DataFrame([{
                "Date": today_str,
                "Registered": registered,
                "Eligible": eligible,
                "Total": total_today,
                "Reg_Change": reg_change,
                "Elig_Change": elig_change,
                "Total_Change": total_change
            }])

            if os.path.exists(HISTORY_FILE):
                hist = pd.read_csv(HISTORY_FILE)
                hist = hist[hist["Date"] != today_str]
                hist = pd.concat([hist, new_entry], ignore_index=True)
            else:
                hist = new_entry
                
            hist.to_csv(HISTORY_FILE, index=False)
            print(f"✅ History updated in {HISTORY_FILE}")
            return hist
        else:
            print("❌ Error: Could not find 'TOTAL REGISTERED' or 'TOTAL ELIGIBLE' labels.")
            return None

    except Exception as e:
        print(f"❌ Error parsing file: {e}")
        return None

if __name__ == "__main__":
    update_silver_inventory()