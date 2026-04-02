import json
import os 
import csv
import sys
import pandas as pd
import glob
from datetime import datetime, timedelta
import subprocess
import xml.etree.ElementTree as ET

# Define the Master Data Directory
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")

# 1. Save the real terminal output channel
original_stdout = sys.stdout

# 2. DEBUG MODE: Set this to False to mute the script for production
DEBUG_MODE = True

if not DEBUG_MODE:
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

try:
    from fredapi import Fred
except ImportError:
    Fred = None
try:
    import nasdaqdatalink
except ImportError:
    nasdaqdatalink = None
# Optional: FRED API Key (for DXY, etc.)
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
import yfinance as yf
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- CONFIGURATION ---

# Alpha Vantage API Key for DXY
ALPHA_VANTAGE_KEY = "YW2UOXMBSGLQ7MZK"

def get_latest_comex_registered():
    """Retrieves the absolute latest 'Registered' ounce count from the history CSV."""
    try:
        # POINTING DIRECTLY TO THE CME_DATA FOLDER
        csv_path = os.path.join(DATA_DIR, "comex_inventory_history.csv")
        
        if not os.path.exists(csv_path):
            print(f"[TACTICAL] Error: {csv_path} not found.")
            return 0
            
        df = pd.read_csv(csv_path)
        # Grab the last row in the 'Registered' column
        latest_val = df['Registered'].iloc[-1]
        return float(latest_val)
    except Exception as e:
        print(f"[TACTICAL] Error reading inventory history: {e}")
        return 0

def find_latest_volume_dashboard(lookback_days=7):
    """Checks the last X days for the most recent volume_dashboard.txt."""
    today = datetime.now()
    for i in range(lookback_days + 1):
        check_date = today - timedelta(days=i)
        folder_str = check_date.strftime("%b-%d-%y")
        path = os.path.join(DATA_DIR, folder_str, "volume_dashboard.txt")
        
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def get_physical_arbitrage_xml():
    """Runs ebay.py and parses its XML output to append to the tactical ruling."""
    
    # EXPLICIT PATH: Tells the system exactly where ebay.py is located on your Mac
    ebay_script = os.path.expanduser("~/Desktop/Python2026/ebay.py")
    
    # Safety Check
    if not os.path.exists(ebay_script):
        print(f"[ARBITRAGE] Error: Could not find script at {ebay_script}")
        return None
        
    try:
        # Run ebay.py silently and capture the stdout
        output = subprocess.check_output(
            [sys.executable, ebay_script], 
            text=True, 
            timeout=120 # Playwright takes time, so give it 2 mins
        )
        
        # Parse the raw string output into an XML Element
        arb_root = ET.fromstring(output)
        return arb_root
        
    except subprocess.TimeoutExpired:
        print("[ARBITRAGE] Error: Scraper timed out.")
    except Exception as e:
        print(f"[ARBITRAGE] Error extracting data: {e}")
        
    return None

# Helper: Fetch last close price for a ticker (Yahoo)
def get_yf_price(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            return price
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return None

# Helper: Fetch last close and change for a ticker (Yahoo)
def get_yf_price_and_change(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            change = price - hist['Close'].iloc[-2] if len(hist) > 1 else 0.0
            return price, change
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return None, None

def get_shfe_data_comprehensive():
    """Uses AKShare SGE Benchmark and YFinance FX to calculate arb metrics."""
    try:
        # 1. Get Shanghai Spot Benchmark (CNY/kg)
        df = ak.spot_silver_benchmark_sge()
        latest = df.iloc[-1]
        cny_kg = latest['晚盘价'] if latest['晚盘价'] > 0 else latest['早盘价']
        
        # 2. Get Live USD/CNY Exchange Rate
        usd_cny = get_yf_price("CNY=X") or 7.24 # Fallback
        
        # 3. Get COMEX Silver Price (USD/oz)
        comex = get_yf_price("SI=F")
        
        if cny_kg and usd_cny and comex:
            # MATH ENGINE
            # a. Price per KG in USD
            usd_kg = cny_kg / usd_cny
            
            # b. Price per OZ in USD (1kg = 32.1507 troy oz)
            usd_oz_raw = usd_kg / 32.1507
            
            # c. Real Premium (Strip 13% Chinese VAT to compare to world spot)
            usd_oz_no_tax = ( (cny_kg / 1.13) / usd_cny ) / 32.1507
            premium = usd_oz_no_tax - comex
            
            return {
                "cny_kg": round(cny_kg, 2),
                "usd_kg": round(usd_kg, 2),
                "usd_oz": round(usd_oz_raw, 2),
                "comex": round(comex, 2),
                "premium": round(premium, 2)
            }
    except Exception as e:
        pass
    return None

# 1. 10Y Treasury Yield (TNX) and /ZN Futures
def get_treasury_yield_and_zn():
    tnx = get_yf_price("^TNX")  # Yield in percent
    zn = get_yf_price("ZN=F")   # 10Y Note Futures
    return tnx, zn

# 2. Crude Oil Futures (/CL, /BZ)
def get_crude_oil():
    cl, cl_chg = get_yf_price_and_change("CL=F")
    bz, bz_chg = get_yf_price_and_change("BZ=F")
    return (cl, cl_chg), (bz, bz_chg)

# 3. VIX Futures (/VX)
def get_vix():
    # Use ^VIX (spot index) instead of VX=F (futures)
    vix, vix_chg = get_yf_price_and_change("^VIX")
    return vix, vix_chg

# 4. US Dollar Index (DXY)
def get_dxy():
    # Try yfinance first
    dxy, dxy_chg = get_yf_price_and_change("DX-Y.NYB")
    if dxy is not None and dxy_chg is not None:
        return dxy, dxy_chg

    # Try yfinance with 'DXY' symbol
    dxy2, dxy2_chg = get_yf_price_and_change("DXY")
    if dxy2 is not None:
        print("[DXY] Source: yfinance 'DXY'")
        return dxy2, dxy2_chg

    # Try FRED (Federal Reserve Economic Data)
    if Fred and FRED_API_KEY:
        try:
            fred = Fred(api_key=FRED_API_KEY)
            dxy_fred = fred.get_series_latest_release('DTWEXBGS')
            if dxy_fred is not None:
                print("[DXY] Source: FRED DTWEXBGS")
                return float(dxy_fred), None
        except Exception as e:
            print(f"Error fetching DXY from FRED: {e}")

    # Try Alpha Vantage
    try:
        url = f"https://www.alphavantage.co/query?function=DX&apikey={ALPHA_VANTAGE_KEY}"
        r = requests.get(url, timeout=10)
        j = r.json()
        # Alpha Vantage may not have direct DXY, so synthesize if needed
        if 'Realtime Currency Exchange Rate' in j:
            # Not DXY, but a currency rate
            return None, None
        # Try to parse DXY from time series
        for key in j:
            if 'Time Series' in key:
                latest = list(j[key].values())[0]
                price = float(latest.get('4. close', 0))
                return price, None
        # If not, try to synthesize DXY from FX rates (EUR, JPY, GBP, CAD, SEK, CHF)
        # DXY = 0.576*EUR/USD + 0.136*USD/JPY + 0.119*GBP/USD + 0.091*USD/CAD + 0.042*USD/SEK + 0.036*USD/CHF
        fx_pairs = {
            'EURUSD': ('EUR', 'USD'),
            'USDJPY': ('USD', 'JPY'),
            'GBPUSD': ('GBP', 'USD'),
            'USDCAD': ('USD', 'CAD'),
            'USDSEK': ('USD', 'SEK'),
            'USDCHF': ('USD', 'CHF'),
        }
        weights = {'EURUSD':0.576, 'USDJPY':0.136, 'GBPUSD':0.119, 'USDCAD':0.091, 'USDSEK':0.042, 'USDCHF':0.036}
        fx_vals = {}
        for pair in fx_pairs:
            url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={fx_pairs[pair][0]}&to_currency={fx_pairs[pair][1]}&apikey={ALPHA_VANTAGE_KEY}"
            r = requests.get(url, timeout=10)
            j = r.json()
            try:
                fx_vals[pair] = float(j['Realtime Currency Exchange Rate']['5. Exchange Rate'])
            except:
                fx_vals[pair] = None
        if all(fx_vals.values()):
            dxy_val = (
                weights['EURUSD'] * fx_vals['EURUSD'] +
                weights['USDJPY'] * fx_vals['USDJPY'] +
                weights['GBPUSD'] * fx_vals['GBPUSD'] +
                weights['USDCAD'] * fx_vals['USDCAD'] +
                weights['USDSEK'] * fx_vals['USDSEK'] +
                weights['USDCHF'] * fx_vals['USDCHF']
            )
            return dxy_val, None
    except Exception as e:
        print(f"Error fetching DXY from Alpha Vantage: {e}")

    # Fallback: scrape Investing.com
    try:
        url = "https://www.investing.com/indices/us-dollar-index"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        price_span = soup.find("span", {"data-test": "instrument-price-last"})
        if price_span:
            price = float(price_span.text.replace(",", ""))
            return price, None
    except Exception as e:
        print(f"Error scraping DXY from Investing.com: {e}")
    return None, None

# 5. Gold/Silver Ratio (GSR) & Precious Metals
def get_gsr():
    gold = get_yf_price("GC=F")
    silver = get_yf_price("SI=F")
    if gold and silver and silver != 0:
        return (gold / silver), gold, silver
    return None, gold, silver

# 6. SHFE Silver Premium (Scrape SHFE, compare to COMEX, convert to USD)
def get_shfe_silver_premium():
    # Try yfinance with 'SILV.SHF' (alternate SHFE silver ticker)
    try:
        shfe2 = get_yf_price("SILV.SHF")
        if shfe2:
            cny_usd = get_yf_price("CNY=X")
            shfe_usd_oz = shfe2 / 31.1035 / cny_usd if cny_usd else None
            comex = get_yf_price("SI=F")
            if shfe_usd_oz and comex:
                premium = shfe_usd_oz - comex
                print("[SHFE] Source: yfinance 'SILV.SHF'")
                return shfe_usd_oz, comex, premium
    except Exception as e:
        print(f"Error fetching SHFE from Yahoo (SILV.SHF): {e}")

    # Try Quandl/Nasdaq Data Link for SHFE Silver
    if nasdaqdatalink:
        try:
            # Example: 'SHFE/AG' (check if available)
            data = nasdaqdatalink.get("SHFE/AG")
            if not data.empty:
                shfe_val = float(data['Settle'].iloc[-1])
                cny_usd = get_yf_price("CNY=X")
                shfe_usd_oz = shfe_val / 31.1035 / cny_usd if cny_usd else None
                comex = get_yf_price("SI=F")
                if shfe_usd_oz and comex:
                    premium = shfe_usd_oz - comex
                    print("[SHFE] Source: Nasdaq Data Link 'SHFE/AG'")
                    return shfe_usd_oz, comex, premium
        except Exception as e:
            print(f"Error fetching SHFE from Nasdaq Data Link: {e}")

    # Try Yahoo Finance symbol first
    try:
        shfe = get_yf_price("AG0.SHF")
        if shfe:
            cny_usd = get_yf_price("CNY=X")
            shfe_usd_oz = shfe / 31.1035 / cny_usd if cny_usd else None
            comex = get_yf_price("SI=F")
            if shfe_usd_oz and comex:
                premium = shfe_usd_oz - comex
                return shfe_usd_oz, comex, premium
    except Exception as e:
        print(f"Error fetching SHFE from Yahoo: {e}")

    # Fallback: scrape SHFE
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.shfe.com.cn/en/marketdata/realmarket.html?param=AG")
            page.wait_for_timeout(3000)
            content = page.content()
            import re
            match = re.search(r'Last Price.*?(\d+[,.]?\d*)', content)
            shfe_price = float(match.group(1).replace(',', '')) if match else None
            browser.close()
        if shfe_price:
            cny_usd = get_yf_price("CNY=X")
            shfe_usd_oz = shfe_price / 31.1035 / cny_usd if cny_usd else None
            comex = get_yf_price("SI=F")
            if shfe_usd_oz and comex:
                premium = shfe_usd_oz - comex
                return shfe_usd_oz, comex, premium
    except Exception as e:
        print(f"Error scraping SHFE: {e}")
    return None, None, None

# 7 & 8. GEX and DIX (SqueezeMetrics, scrape if possible)
def get_gex_dix():
    gex, dix = None, None
    # Try public CSVs or GitHub for GEX/DIX (example: SqueezeMetrics public CSV, if available)
    # Example placeholder: https://raw.githubusercontent.com/SqueezeMetrics/monitor/main/gex.csv
    gex, dix = None, None
    try:
        gex_url = "https://raw.githubusercontent.com/SqueezeMetrics/monitor/main/gex.csv"
        r = requests.get(gex_url, timeout=10)
        if r.status_code == 200:
            lines = r.text.splitlines()
            if len(lines) > 1:
                last = lines[-1].split(',')
                gex = float(last[1])
                print("[GEX] Source: SqueezeMetrics GitHub CSV")
    except Exception as e:
        print(f"Error fetching GEX from GitHub CSV: {e}")
    try:
        dix_url = "https://raw.githubusercontent.com/SqueezeMetrics/monitor/main/dix.csv"
        r = requests.get(dix_url, timeout=10)
        if r.status_code == 200:
            lines = r.text.splitlines()
            if len(lines) > 1:
                last = lines[-1].split(',')
                dix = float(last[1])
                print("[DIX] Source: SqueezeMetrics GitHub CSV")
    except Exception as e:
        print(f"Error fetching DIX from GitHub CSV: {e}")
    return gex, dix

# 9. Credit Spreads (ICE BofA High Yield OAS) with Time Deltas
def get_credit_spread():
    # The exact endpoint from the official documentation
    url = "https://api.stlouisfed.org/fred/series/observations"
    
    # We increase the limit to 300 to capture a full year of trading days (approx 252 days/year)
    params = {
        "series_id": "BAMLH0A0HYM2",
        "api_key": "cd61da3e0d2880811750290cf34a73d3", # Reverted to your secure variable
        "file_type": "json",
        "sort_order": "desc", # Gets the newest dates first
        "limit": 300          
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        if "observations" in data and len(data["observations"]) > 0:
            # First, clean the data: Filter out all the '.' bank holidays and convert to floats
            valid_obs = [float(day["value"]) for day in data["observations"] if day["value"] != '.']
            
            if len(valid_obs) > 0:
                latest = valid_obs[0]
                
                # Retrieve historical data points based on average trading days
                day_1 = valid_obs[1] if len(valid_obs) > 1 else latest
                week_1 = valid_obs[5] if len(valid_obs) > 5 else latest
                month_1 = valid_obs[21] if len(valid_obs) > 21 else latest
                year_1 = valid_obs[252] if len(valid_obs) > 252 else latest
                
                # Calculate the exact changes
                chg_1d = latest - day_1
                chg_1w = latest - week_1
                chg_1m = latest - month_1
                chg_1y = latest - year_1
                
                ## can enable for debug
                ##print("[CREDIT SPREAD] Source: FRED Official API (Calculated Deltas)")
                
                # We return a dictionary instead of a single number
                return {
                    "latest": latest,
                    "1D": chg_1d,
                    "1W": chg_1w,
                    "1M": chg_1m,
                    "1Y": chg_1y
                }
                
    except Exception as e:
        print(f"Error fetching from official FRED API: {e}")
        
    return None

# 10. Liquidity Plumbing (ON RRP & Fed Balance Sheet) with Time Deltas
def get_liquidity_plumbing():
    url = "https://api.stlouisfed.org/fred/series/observations"

    # Mini-engine to fetch, filter, and calculate deltas for any series
    def fetch_series_with_deltas(series_id, divisor=1.0):
        params = {
            "series_id": series_id,
            "api_key": "cd61da3e0d2880811750290cf34a73d3",
            "file_type": "json",
            "sort_order": "desc",
            "limit": 300 # Pull ~1 year of data
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            if "observations" in data and len(data["observations"]) > 0:
                # Filter out holidays and apply the divisor (to convert to Billions)
                valid_obs = [float(day["value"]) / divisor for day in data["observations"] if day["value"] != '.']

                if len(valid_obs) > 0:
                    latest = valid_obs[0]
                    
                    # Target historical offsets (approximate trading days)
                    day_1 = valid_obs[1] if len(valid_obs) > 1 else latest
                    week_1 = valid_obs[5] if len(valid_obs) > 5 else latest
                    month_1 = valid_obs[21] if len(valid_obs) > 21 else latest
                    year_1 = valid_obs[252] if len(valid_obs) > 252 else latest

                    return {
                        "latest": latest,
                        "1D": latest - day_1,
                        "1W": latest - week_1,
                        "1M": latest - month_1,
                        "1Y": latest - year_1
                    }
        except Exception as e:
            print(f"Error fetching {series_id} from FRED API: {e}")
        return None

    # RRP is already in Billions (Divisor = 1.0)
    rrp_data = fetch_series_with_deltas("RRPONTSYD", divisor=1.0)
    
    # WALCL is in Millions. (Divisor = 1000.0 to convert to Billions)
    walcl_data = fetch_series_with_deltas("WALCL", divisor=1000.0)

    if rrp_data or walcl_data:
        #can enable later for debug
        #print("[LIQUIDITY] Source: FRED Official API (Calculated Deltas)")

        return rrp_data, walcl_data

# 11. The Catalyst Calendar (Tier-1 US Economic Data)
def get_catalyst_calendar():
    # ForexFactory provides a free, unauthenticated XML feed of the week's events
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # ForexFactory XML formats dates as MM-DD-YYYY
    today_str = datetime.now().strftime("%m-%d-%Y")
    tripwires = []

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            
            for event in root.findall('event'):
                country = event.find('country').text
                impact = event.find('impact').text
                date_str = event.find('date').text
                
                # We ONLY care about High Impact (Tier-1) USD events happening TODAY
                if country == "USD" and impact == "High" and date_str == today_str:
                    time_str = event.find('time').text # e.g., "8:30am"
                    title = event.find('title').text   # e.g., "CPI m/m" or "FOMC Statement"
                    
                    tripwires.append({
                        "time": time_str,
                        "event": title
                    })
        if len(tripwires) > 0:            
            print(f"[CATALYST] Source: ForexFactory XML ({len(tripwires)} Tier-1 Events Today)")
            return tripwires
        else:
            return None
        
    except Exception as e:
        print(f"Error fetching Catalyst Calendar: {e}")
        return None

# 12. Vlad Macro Risk Index (VMRI)
def calculate_vmri(dxy, tnx, oas, vix):
    # Ensure all data points are available
    if None in (dxy, tnx, oas, vix):
        return None, "INCOMPLETE DATA"
        
    # 1. Base Stress (The MMRI Foundation)
    base_stress = (dxy * tnx) / 1.61
    
    # 2. The Credit Multiplier (Baseline 4.00)
    credit_multiplier = oas / 4.00
    
    # 3. The Volatility Premium (Baseline 20.00)
    vol_premium = vix / 20.00
    
    # The Ultimate Apex Score
    vmri_score = base_stress * credit_multiplier * vol_premium
    
    # The Actionable Risk Tiers
    if vmri_score < 150:
        tier = "LOW RISK (Complacent / Squeeze Danger)"
    elif 150 <= vmri_score < 250:
        tier = "MODERATE RISK (Standard Operating Environment)"
    elif 250 <= vmri_score < 350:
        tier = "ELEVATED RISK (Hedge Triggers Active)"
    else:
        tier = "SYSTEMIC THREAT (Crash Dynamics Active)"
        
    return vmri_score, tier

def log_macro_ledger(ledger_data):
    """Logs data to the master ledger with auto-schema upgrade for Paper:Physical metrics."""
    import pandas as pd
    import csv
    
    # Establish file path
    data_dir = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
    os.makedirs(data_dir, exist_ok=True)
    file_path = os.path.join(data_dir, "macro_master_ledger.csv")
    file_exists = os.path.isfile(file_path)

    # UPDATED HEADERS: Added Institutional Silver Metrics
    headers = [
        "Datetime", "VMRI_Score", "Threat_Tier", "DXY", "DXY_Change", 
        "10Y_Yield", "ZN_Futures", "High_Yield_OAS", "VIX", "VIX_Change", 
        "WTI_Crude", "Brent_Crude", "Gold_Price", "Gold_Silver_Ratio", "SHFE_Silver_USD", 
        "COMEX_Silver", "SHFE_Premium", "GEX", "DIX", "Reverse_Repo_BN", "Fed_Balance_Sheet_BN",
        "Retail_Silver_Cheapest", "Retail_Silver_Avg", "Silver_OI", "Paper_Physical_Ratio"
    ]

    # --- ADVANCED BACKWARDS COMPATIBILITY UPGRADE ENGINE ---
    if file_exists:
        try:
            # Read only the first row to check column names
            existing_df_sample = pd.read_csv(file_path, nrows=0)
            existing_cols = existing_df_sample.columns.tolist()
            
            # Identify which headers are missing from the current file
            missing_cols = [col for col in headers if col not in existing_cols]
            
            if missing_cols:
                print(f"[LEDGER] Schema Mismatch Detected. Injecting missing columns: {missing_cols}")
                # Load the full file, add missing columns as NaN, and save
                df = pd.read_csv(file_path)
                for col in missing_cols:
                    df[col] = float("nan")
                
                # Reindex to ensure column order matches our new 'headers' list
                df = df.reindex(columns=headers)
                df.to_csv(file_path, index=False)
                print("[LEDGER] CSV successfully upgraded to new schema.")
        except Exception as e:
            print(f"[LEDGER] Warning: Auto-upgrade failed: {e}")

    # --- DATA APPEND LOGIC ---
    with open(file_path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write headers if file is brand new
        if not file_exists or os.stat(file_path).st_size == 0:
            writer.writerow(headers)
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Build the row dynamically based on the updated header list
        row = [current_time]
        for col in headers[1:]: 
            val = ledger_data.get(col)
            # Log as raw value or "NaN" string for easier loading in JS/Chart.js
            row.append(val if val is not None else "NaN")
            
        writer.writerow(row)

# Add this function to your tactical_ruling.py
def get_macro_calendar_native():
    """Fetches High/Medium USD events for the next 7 days with weekend-gap protection."""
    urls = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    today = datetime.now()
    # Robust date matching: Catch both 03-21 and 3-21 formats
    target_dates = [(today + timedelta(days=i)).strftime('%m-%d-%Y') for i in range(8)]
    target_dates_alt = [(today + timedelta(days=i)).strftime('%-m-%-d-%Y') for i in range(8)]
    all_targets = set(target_dates + target_dates_alt)
    
    events = []
    seen_events = set()

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200: continue
            
            root = ET.fromstring(resp.content)
            for event in root.findall('event'):
                if event.findtext('country', '') == 'USD' and \
                   event.findtext('impact', '') in ['High', 'Medium']:
                    
                    date = event.findtext('date', '')
                    if date in all_targets:
                        title = event.findtext('title', '')
                        time = event.findtext('time', '')
                        
                        # Prevent duplicates across feed overlaps
                        event_key = f"{date}-{time}-{title}"
                        if event_key in seen_events: continue
                        seen_events.add(event_key)

                        events.append({
                            "date": date,
                            "time": time,
                            "impact": event.findtext('impact', ''),
                            "title": title,
                            "forecast": event.findtext('forecast', 'N/A'),
                            "previous": event.findtext('previous', 'N/A')
                        })
        except: continue
    return events

def get_latest_comex_inventory():
    """Finds and parses the latest Daily Metal Stocks CSV to get total Registered silver."""
    try:
        data_dir = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
        # Look for the latest silver_stocks CSV file
        import glob
        files = glob.glob(os.path.join(data_dir, "**", "silver_stocks*.csv"), recursive=True)
        if not files: return 0
        
        latest_file = max(files, key=os.path.getmtime)
        df = pd.read_csv(latest_file, skiprows=7)
        # Sum the 'TOTAL TODAY' column (index 7) where rows are 'Registered'
        registered_val = df[df.iloc[:, 0].str.contains("Registered", na=False)].iloc[:, 7].astype(float).sum()
        return registered_val
    except:
        return 0


def print_tactical_ruling():
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    import akshare as ak

    # --- TOP LEVEL DATA PREP (PAPER vs PHYSICAL) ---
    physical_inventory_oz = get_latest_comex_registered()
    silver_oi = 0
    paper_claims_oz = 0
    leverage_ratio = 0
    
    dash_path = find_latest_volume_dashboard()
    if dash_path:
        try:
            dash_tree = ET.parse(dash_path)
            dash_root = dash_tree.getroot()
            silver_node = dash_root.find("silver")
            if silver_node is not None:
                days = silver_node.findall("day")
                if days:
                    # Get the most recent day's OI from the XML
                    latest_day = days[-1]
                    silver_oi = float(latest_day.get("open_interest"))
                    paper_claims_oz = silver_oi * 5000 # 1 contract = 5000 oz
        except Exception as e:
            print(f"[TACTICAL] Dashboard Parse Error: {e}")

    if physical_inventory_oz > 0:
        leverage_ratio = paper_claims_oz / physical_inventory_oz

    # Now start building the XML
    root = ET.Element("tactical_ruling")
    root.set("generated", datetime.now().strftime('%Y-%m-%d %H:%M'))



    # 1. Macro Kill-Switches
    tnx, zn = get_treasury_yield_and_zn()
    macro = ET.SubElement(root, "macro_kill_switches")
    ET.SubElement(macro, "ten_year_treasury").text = f"{tnx:.2f}" if tnx else "unavailable"
    ET.SubElement(macro, "zn_futures").text = str(zn) if zn else "unavailable"

    # 2. Crude Oil Complex
    (cl, cl_chg), (bz, bz_chg) = get_crude_oil()
    crude = ET.SubElement(root, "crude_oil")
    wti = ET.SubElement(crude, "wti")
    ET.SubElement(wti, "price").text = f"{cl:.2f}" if cl else "unavailable"
    ET.SubElement(wti, "change").text = f"{cl_chg:+.2f}" if cl_chg else "unavailable"
    
    brent = ET.SubElement(crude, "brent")
    ET.SubElement(brent, "price").text = f"{bz:.2f}" if bz else "unavailable"
    ET.SubElement(brent, "change").text = f"{bz_chg:+.2f}" if bz_chg else "unavailable"

    # 3. The Catalyst Calendar
    tripwires = get_catalyst_calendar()
    catalyst_elem = ET.SubElement(root, "catalyst_calendar")
    if tripwires:
        ET.SubElement(catalyst_elem, "status").text = "ARMED (Tier-1 Data Today)"
        for alert in tripwires:
            event_elem = ET.SubElement(catalyst_elem, "tripwire")
            ET.SubElement(event_elem, "time_est").text = alert["time"]
            ET.SubElement(event_elem, "event").text = alert["event"]
    elif tripwires is not None:
        ET.SubElement(catalyst_elem, "status").text = "CLEAR (No Tier-1 Data Today)"
    else:
        ET.SubElement(catalyst_elem, "status").text = "unavailable"

    # 4. Credit Markets (FRED OAS)
    credit_data = get_credit_spread()
    credit_elem = ET.SubElement(root, "credit_markets")
    if credit_data:
        ET.SubElement(credit_elem, "high_yield_oas_spread").text = f"{credit_data['latest']:.2f}"
        ET.SubElement(credit_elem, "change_1D").text = f"{credit_data['1D']:+.2f}"
        ET.SubElement(credit_elem, "change_1W").text = f"{credit_data['1W']:+.2f}"
        ET.SubElement(credit_elem, "change_1M").text = f"{credit_data['1M']:+.2f}"
        ET.SubElement(credit_elem, "change_1Y").text = f"{credit_data['1Y']:+.2f}"
    else:
        ET.SubElement(credit_elem, "high_yield_oas_spread").text = "unavailable"

    # 5. Liquidity Plumbing (RRP / Fed Balance Sheet)
    rrp_data, walcl_data = get_liquidity_plumbing()
    liquidity_elem = ET.SubElement(root, "liquidity_plumbing")
    
    rrp_elem = ET.SubElement(liquidity_elem, "reverse_repo_bn")
    if rrp_data:
        ET.SubElement(rrp_elem, "latest").text = f"{rrp_data['latest']:.2f}"
        ET.SubElement(rrp_elem, "change_1D").text = f"{rrp_data['1D']:+.2f}"
        ET.SubElement(rrp_elem, "change_1M").text = f"{rrp_data['1M']:+.2f}"
    
    walcl_elem = ET.SubElement(liquidity_elem, "fed_balance_sheet_bn")
    if walcl_data:
        ET.SubElement(walcl_elem, "latest").text = f"{walcl_data['latest']:.2f}"
        ET.SubElement(walcl_elem, "change_1D").text = f"{walcl_data['1D']:+.2f}"
        ET.SubElement(walcl_elem, "change_1M").text = f"{walcl_data['1M']:+.2f}"

    # 6. VIX & DXY
    vx, vx_chg = get_vix()
    vix_elem = ET.SubElement(root, "vix")
    ET.SubElement(vix_elem, "value").text = f"{vx:.2f}" if vx else "unavailable"
    ET.SubElement(vix_elem, "change").text = f"{vx_chg:+.2f}" if vx_chg else "unavailable"

    dxy, dxy_chg = get_dxy()
    dxy_elem = ET.SubElement(root, "dxy")
    ET.SubElement(dxy_elem, "value").text = f"{dxy:.2f}" if dxy else "unavailable"
    ET.SubElement(dxy_elem, "change").text = f"{dxy_chg:+.2f}" if dxy_chg else "unavailable"

   # 7. Physical Arbitrage (SHFE/SGE)
    shfe_elem = ET.SubElement(root, "shfe_silver")
    
    # Initialize variables so the ledger can access them even if the scrape fails
    shfe_usd_oz = None
    comex_spot_price = None
    shfe_premium_val = None
    
    try:
        sge_df = ak.spot_silver_benchmark_sge()
        latest_sge = sge_df.iloc[-1]
        cny_kg = latest_sge['晚盘价'] if latest_sge['晚盘价'] > 0 else latest_sge['早盘价']
        usd_cny = get_yf_price("CNY=X") or 7.24
        comex = get_yf_price("SI=F")
        
        if cny_kg and usd_cny and comex:
            usd_kg = cny_kg / usd_cny
            shfe_usd_oz = usd_kg / 32.1507
            usd_oz_no_tax = ((cny_kg / 1.13) / usd_cny) / 32.1507
            comex_spot_price = comex
            shfe_premium_val = usd_oz_no_tax - comex
            
            ET.SubElement(shfe_elem, "cny_per_kg").text = f"¥{cny_kg:,.2f}"
            ET.SubElement(shfe_elem, "usd_per_kg").text = f"${usd_kg:,.2f}"
            ET.SubElement(shfe_elem, "usd_per_oz").text = f"${shfe_usd_oz:,.2f}"
            ET.SubElement(shfe_elem, "comex_spot").text = f"${comex:,.2f}"
            ET.SubElement(shfe_elem, "premium").text = f"{shfe_premium_val:+.2f}"
    except:
        ET.SubElement(shfe_elem, "status").text = "unavailable"

    # 8. Precious Metals & GSR
    gsr, gold_price, silver_price = get_gsr()
    ET.SubElement(root, "gold_silver_ratio").text = f"{gsr:.2f}" if gsr else "unavailable"
    ET.SubElement(root, "gold_price").text = f"{gold_price:.2f}" if gold_price else "unavailable"

    # 9. Institutional Positioning (GEX/DIX)
    gex, dix = get_gex_dix()
    ET.SubElement(root, "gex").text = str(gex) if gex else "unavailable"
    ET.SubElement(root, "dix").text = str(dix) if dix else "unavailable"

    # 10. VLAD MACRO RISK INDEX (VMRI)
    oas_val = credit_data['latest'] if credit_data else None
    vmri_score, vmri_tier = calculate_vmri(dxy, tnx, oas_val, vx)
    
    vmri_elem = ET.SubElement(root, "VLAD_MACRO_RISK_INDEX")
    if vmri_score:
        ET.SubElement(vmri_elem, "score").text = f"{vmri_score:.2f}"
        ET.SubElement(vmri_elem, "threat_level").text = vmri_tier
        details = ET.SubElement(vmri_elem, "mechanics")
        ET.SubElement(details, "base_stress").text = f"{(dxy * tnx) / 1.61:.2f}"
        ET.SubElement(details, "credit_multiplier").text = f"{oas_val / 4.00:.2f}x"
        ET.SubElement(details, "volatility_premium").text = f"{vx / 20.00:.2f}x"
    else:
        ET.SubElement(vmri_elem, "score").text = "UNAVAILABLE"

    # --- NEW: SECTION 11. PHYSICAL RETAIL ARBITRAGE (EBAY) ---
    arb_xml = get_physical_arbitrage_xml()
    retail_cheapest = None
    retail_avg = None

    if arb_xml is not None:
        root.append(arb_xml)
        
        # Parse the XML to calculate metrics for the ledger
        listings = arb_xml.findall('listing')
        costs = []
        for l in listings:
            try:
                # Strip the dollar sign and convert to float
                cost = float(l.get('total_cost').replace('$', ''))
                costs.append(cost)
            except:
                continue
                
        if costs:
            retail_cheapest = min(costs)
            retail_avg = sum(costs) / len(costs)
            
    else:
        arb_fail = ET.SubElement(root, "physical_arbitrage")
        arb_fail.set("status", "unavailable_or_timeout")

    # 12. Catalyst Events
    macro_events = get_macro_calendar_native()
    calendar_root = ET.SubElement(root, "upcoming_macro_events")
    
    if macro_events:
        for ev in macro_events:
            event_node = ET.SubElement(calendar_root, "event")
            event_node.set("date", ev['date'])
            event_node.set("time", ev['time'])
            event_node.set("impact", ev['impact'])
            event_node.set("title", ev['title'])
            event_node.set("forecast", ev['forecast'])
            event_node.set("previous", ev['previous'])
    else:
        ET.SubElement(calendar_root, "status").text = "No High/Medium impact events scheduled."

    # --- UPDATED SECTION 13 (Now uses variables from top) ---
    comex_risk = ET.SubElement(root, "comex_default_risk")
    ET.SubElement(comex_risk, "paper_claims_oz").text = f"{paper_claims_oz:,.0f}"
    ET.SubElement(comex_risk, "physical_registered_oz").text = f"{physical_inventory_oz:,.0f}"
    ET.SubElement(comex_risk, "leverage_ratio").text = f"{leverage_ratio:.2f}:1"
    
    # Trigger Status Tiers
    status_text = "NOMINAL"
    if leverage_ratio >= 40: status_text = "CRITICAL"
    elif leverage_ratio >= 30: status_text = "HIGH"
    elif leverage_ratio >= 15: status_text = "ELEVATED"
    ET.SubElement(comex_risk, "status").text = status_text

   # --- THE PIPE: SAVE TO DISK ---
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed = minidom.parseString(xml_str)
    xml_output = parsed.toprettyxml(indent="  ")

    data_dir = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
    today_str = datetime.now().strftime("%b-%d-%y")
    daily_dir = os.path.join(data_dir, today_str)
    os.makedirs(daily_dir, exist_ok=True)
    
    output_path = os.path.join(daily_dir, "tactical_ruling.txt")
    
    with open(output_path, "w") as f:
        f.write(xml_output)

    # Fire master ledger entry with ALL 25 COLUMNS MAPPED
    ledger_data = {
        "VMRI_Score": vmri_score, 
        "Threat_Tier": vmri_tier, 
        "DXY": dxy, 
        "DXY_Change": dxy_chg,
        "10Y_Yield": tnx, 
        "ZN_Futures": zn,
        "High_Yield_OAS": oas_val, 
        "VIX": vx, 
        "VIX_Change": vx_chg,
        "WTI_Crude": cl, 
        "Brent_Crude": bz,
        "Gold_Price": gold_price, 
        "Gold_Silver_Ratio": gsr, 
        "SHFE_Silver_USD": shfe_usd_oz,
        "COMEX_Silver": comex_spot_price if comex_spot_price else silver_price,
        "SHFE_Premium": shfe_premium_val,
        "GEX": gex, 
        "DIX": dix,
        "Reverse_Repo_BN": rrp_data['latest'] if rrp_data else None,
        "Fed_Balance_Sheet_BN": walcl_data['latest'] if walcl_data else None,
        "Retail_Silver_Cheapest": retail_cheapest, 
        "Retail_Silver_Avg": retail_avg,
        "Silver_OI": silver_oi,                      # NEW: Open Interest Contracts
        "Paper_Physical_Ratio": round(leverage_ratio, 2) # NEW: The 7.17 or 44.0 value
    }
    
    # Fire the updated log function
    log_macro_ledger(ledger_data)
    # --- TRANSMIT THE PAYLOAD ---
    sys.stdout = original_stdout
    print(xml_output)

if __name__ == "__main__":
    print_tactical_ruling()