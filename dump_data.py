import os
from config import required_env
import pandas as pd
from datetime import datetime
import sys
import yfinance as yf
from core.api_client import api_client
import subprocess

# --- CONFIGURATION ---
from config import DATA_DIR, GOLD_API_KEY

if len(sys.argv) > 1:
    DAILY_DIR = sys.argv[1]
else:
    TODAY_STR = datetime.now().strftime("%b-%d-%y")
    DAILY_DIR = os.path.join(DATA_DIR, TODAY_STR)

INPUT_FILE = os.path.join(DAILY_DIR, "master_market_data.csv")


def get_last_valid_price(ticker_symbol):
    candidates = [ticker_symbol]
    if ticker_symbol.upper() == "SIH27.CMX":
        candidates.extend(["SI=F", "SI=F", "SI=F", "SI"])

    candidates = list(dict.fromkeys(candidates))

    for symbol in candidates:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="7d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                change = hist['Close'].iloc[-1] - hist['Close'].iloc[-2] if len(hist) > 1 else 0.0
                if symbol != ticker_symbol:
                    print(f"⚠️ Fallback used for {ticker_symbol}: {symbol} -> {price}")
                return price, change
        except Exception:
            continue

    print(f"⚠️ No valid price found for {ticker_symbol}; returning zeros")
    return 0.0, 0.0


def fetch_market_prices():
    data = {
        "SLV": {"price": 0.0, "change": 0.0},
        "SIH26": {"price": 0.0, "change": 0.0},
        "SPOT": {"price": 0.0, "change": 0.0},
        "SHFE": {"price": 0.0, "change": 0.0, "usd_oz": 0.0},
        "USDCNY": 7.22
    }
    # SLV ETF (Yahoo)
    data["SLV"]["price"], data["SLV"]["change"] = get_last_valid_price("SLV")
    # COMEX March 2026 (Yahoo)
    data["SIH26"]["price"], data["SIH26"]["change"] = get_last_valid_price("SIH26.CMX")
    # SPOT SILVER (GoldAPI.io)
    try:
        headers = {"x-access-token": GOLD_API_KEY, "Content-Type": "application/json"}
        res = api_client.get("https://www.goldapi.io/api/XAG/USD", headers=headers, timeout=5)
        j = res.json()
        data["SPOT"]["price"] = j.get("price", 0.0)
        data["SPOT"]["change"] = j.get("ch", 0.0)
    except:
        pass
    # USD/CNY Rate
    fx_p, _ = get_last_valid_price("CNY=X")
    if fx_p > 0:
        data["USDCNY"] = fx_p
    # SHFE (Shanghai)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.barchart.com/futures/quotes/XOJ26")
            price_element = page.wait_for_selector("span.last-change", timeout=10000)
            if price_element:
                raw_text = price_element.inner_text()
                clean_price = raw_text.replace(",", "").replace("s", "").strip()
                chg_element = page.query_selector("span.price-change")
                raw_chg = chg_element.inner_text() if chg_element else "0"
                clean_chg = raw_chg.replace(",", "").strip()
                price_val = float(clean_price)
                data["SHFE"]["price"] = price_val
                data["SHFE"]["change"] = float(clean_chg)
                data["SHFE"]["usd_oz"] = (price_val / 1000.0) * 31.1035 / data["USDCNY"]
            browser.close()
    except:
        pass
    return data

def aggregate_data_to_text(volume_df, inventory_df, tactical_text=""):
    import xml.etree.ElementTree as ET
    root = ET.Element("dashboard")

    # Add last updated
    last_updated = ET.SubElement(root, "last_updated")
    last_updated.text = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    if not os.path.exists(INPUT_FILE):
        error = ET.SubElement(root, "error")
        error.text = f"Input file not found: {INPUT_FILE}"
    else:
        df = pd.read_csv(INPUT_FILE)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')

        # S&P 500 (ES)
        es_data = df[df['Product'] == 'E-MINI S&P 500 FUTURE']
        es_elem = ET.SubElement(root, "sp500")
        for _, row in es_data.iterrows():
            entry = ET.SubElement(es_elem, "day")
            entry.set("date", row['Date'].strftime('%Y-%m-%d'))
            entry.set("volume", str(row['Volume']))
            entry.set("open_interest", str(row['Open_Interest']))

        # Silver (SI)
        si_data = df[df['Product'] == 'SILVER FUTURES']
        si_elem = ET.SubElement(root, "silver")
        for _, row in si_data.iterrows():
            entry = ET.SubElement(si_elem, "day")
            entry.set("date", row['Date'].strftime('%Y-%m-%d'))
            entry.set("volume", str(row['Volume']))
            entry.set("open_interest", str(row['Open_Interest']))

        # Smart vs Dumb Money
        sil_data = df[df['Product'] == 'MICRO SILVER FUTURES']
        if len(si_data) > 0 and len(sil_data) > 0:
            smart_elem = ET.SubElement(root, "silver_divergence")
            si_oi_norm = si_data['Open_Interest'] / si_data['Open_Interest'].iloc[0] * 100
            sil_oi_norm = sil_data['Open_Interest'] / sil_data['Open_Interest'].iloc[0] * 100
            for d, inst, retail in zip(si_data['Date'], si_oi_norm, sil_oi_norm):
                entry = ET.SubElement(smart_elem, "day")
                entry.set("date", d.strftime('%Y-%m-%d'))
                entry.set("institutions", f"{inst:.2f}")
                entry.set("retail", f"{retail:.2f}")

        # Put/Call Flow
        es_calls = df[df['Product'] == 'E-MINI S&P 500 CALL']
        es_puts = df[df['Product'] == 'E-MINI S&P 500 PUT']
        if len(es_calls) > 0 and len(es_puts) > 0:
            pc_elem = ET.SubElement(root, "sp500_put_call_flow")
            flow = pd.merge(es_calls[['Date', 'Volume']], es_puts[['Date', 'Volume']], on='Date', suffixes=('_Call', '_Put'))
            flow['PC_Ratio'] = flow['Volume_Put'] / flow['Volume_Call']
            for _, row in flow.iterrows():
                entry = ET.SubElement(pc_elem, "day")
                entry.set("date", row['Date'].strftime('%Y-%m-%d'))
                entry.set("calls", str(row['Volume_Call']))
                entry.set("puts", str(row['Volume_Put']))
                entry.set("ratio", f"{row['PC_Ratio']:.2f}")

        # 10Y Yields
        tn_data = df[df['Product'] == '10Y NOTE FUTURE']
        if len(tn_data) > 0:
            tn_elem = ET.SubElement(root, "ten_year_note")
            for _, row in tn_data.iterrows():
                entry = ET.SubElement(tn_elem, "day")
                entry.set("date", row['Date'].strftime('%Y-%m-%d'))
                entry.set("volume", str(row['Volume']))
                entry.set("oi_change", str(row['OI_Change']))

    # COMEX Inventory
    if inventory_df is not None and not inventory_df.empty:
        inv_df = inventory_df.copy()
        inv_df['Date'] = pd.to_datetime(inv_df['Date'])
        inv_elem = ET.SubElement(root, "comex_inventory")
        for _, row in inv_df.iterrows():
            entry = ET.SubElement(inv_elem, "day")
            entry.set("date", row['Date'].strftime('%Y-%m-%d'))
            entry.set("eligible", f"{row['Eligible']:.2f}")
            entry.set("registered", f"{row['Registered']:.2f}")
            entry.set("total_change", f"{row['Total_Change']:+.0f}")

    # Market Prices
    prices = fetch_market_prices()
    prices_elem = ET.SubElement(root, "market_prices")
    for k, v in prices.items():
        sub = ET.SubElement(prices_elem, k.lower())
        for subk, subv in v.items() if isinstance(v, dict) else []:
            sub.set(subk, str(subv))
        if not isinstance(v, dict):
            sub.text = str(v)

    # Vaults (latest)
    if inventory_df is not None and not inventory_df.empty:
        inv = inventory_df.iloc[-1]
        vaults_elem = ET.SubElement(root, "latest_vaults")
        vaults_elem.set("registered", f"{inv['Registered']:.1f}")
        vaults_elem.set("eligible", f"{inv['Eligible']:.1f}")
        cv = inv['Total_Change']
        cv_fmt = f"{cv/1e6:+.1f}M oz" if abs(cv) >= 1e6 else f"{cv:+,.0f} oz"
        vaults_elem.set("daily_change", cv_fmt)

    # --- Tactical Ruling Section ---
    if tactical_text:
        try:
            # Parse the file as actual XML nodes instead of a raw string
            tactical_parsed = ET.fromstring(tactical_text)
            root.append(tactical_parsed)
        except ET.ParseError:
            error_elem = ET.SubElement(root, "tactical_ruling_error")
            error_elem.text = "Failed to parse tactical_ruling.txt as XML"

    # Write XML to file
    out_path = os.path.join(DAILY_DIR, "volume_dashboard.txt")
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"✅ Data dump ready at {out_path} (XML format)")

if __name__ == "__main__":
    aggregate_data_to_text()
