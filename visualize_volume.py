import os
from config import required_env
import csv
from playwright.sync_api import sync_playwright, TimeoutError
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
import sys
import yfinance as yf
import akshare as ak
import requests

# --- CONFIGURATION ---
from config import DATA_DIR, GOLD_API_KEY

if len(sys.argv) > 1:
    DAILY_DIR = sys.argv[1]
else:
    TODAY_STR = datetime.now().strftime("%b-%d-%y")
    DAILY_DIR = os.path.join(DATA_DIR, TODAY_STR)

INPUT_FILE = os.path.join(DAILY_DIR, "master_market_data.csv")

def get_last_valid_price(ticker_symbol):
    """Deep search for the most recent valid price in the last 7 days for weekend support."""
    candidates = [ticker_symbol]
    if ticker_symbol.upper() == "SIH27.CMX":
        candidates.extend(["SI=F", "SI", "SILVER"])  # fallback to continuous silver futures

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
    """Fetches global snapshots using GoldAPI for Spot, Yahoo for SLV/COMEX, and AKShare for SGE."""
    data = {
        "SLV": {"price": 0.0, "change": 0.0},
        "SIH26": {"price": 0.0, "change": 0.0},
        "SPOT": {"price": 0.0, "change": 0.0},
        "SHFE": {"price": 0.0, "change": 0.0, "usd_oz": 0.0}, # We keep the key name "SHFE" for compatibility
        "USDCNY": 7.22 
    }
    print("▶️ Fetching live global silver prices...")

    # 1. SLV ETF (Yahoo)
    data["SLV"]["price"], data["SLV"]["change"] = get_last_valid_price("SLV")

    # 2. COMEX March 2026 (Yahoo)
    data["SIH26"]["price"], data["SIH26"]["change"] = get_last_valid_price("SIH26.CMX")

    # 3. SPOT SILVER (GoldAPI.io)
    try:
        headers = {"x-access-token": GOLD_API_KEY, "Content-Type": "application/json"}
        res = requests.get("https://www.goldapi.io/api/XAG/USD", headers=headers, timeout=5)
        if res.status_code == 200:
            j = res.json()
            data["SPOT"]["price"] = j.get("price", 0.0)
            data["SPOT"]["change"] = j.get("ch", 0.0)
    except: pass

    # 4. USD/CNY Rate
    fx_p, _ = get_last_valid_price("CNY=X")
    if fx_p > 0: data["USDCNY"] = fx_p

    # 5. SHANGHAI SPOT BENCHMARK (AKShare / SGE)
    try:
        # Pull official Shanghai Silver Benchmark (replaces the broken Playwright scrape)
        df = ak.spot_silver_benchmark_sge()
        if not df.empty:
            latest = df.iloc[-1]
            
            # Use Night session price if available, otherwise Morning
            price_val = float(latest['晚盘价']) if latest['晚盘价'] > 0 else float(latest['早盘价'])
            
            data["SHFE"]["price"] = price_val
            # SGE change isn't always in the benchmark df, defaulting to 0 or calculating if possible
            data["SHFE"]["change"] = 0.0 
            
            # Conversion: (CNY_Price / USDCNY) / 32.1507 (to get USD per troy oz)
            # Or use your specific formula: (price_val / 1000.0) * 31.1035 / data["USDCNY"]
            data["SHFE"]["usd_oz"] = (price_val / data["USDCNY"]) / 32.1507
            
            print(f"✅ Retrieved SGE Silver Benchmark via AKShare: ¥{price_val} CNY/kg")
            
    except Exception as e:
        print(f"⚠️ AKShare SGE Error: {e}")

    return data

def create_charts(df, suffix, title_suffix, inv_df=None):
    sns.set_theme(style="darkgrid")
    plt.rcParams['figure.figsize'] = (14, 7)

    # --- CHART 1: S&P 500 (ES) ---
    es_data = df[df['Product'] == 'E-MINI S&P 500 FUTURE'].copy()
    if not es_data.empty:
        fig, ax1 = plt.subplots()
        ax1.set_title(f'S&P 500 (ES) Conviction {title_suffix}', fontsize=16, fontweight='bold')
        ax1.bar(es_data['Date'], es_data['Volume'], color='skyblue', alpha=0.5, label='Volume')
        ax1.set_ylabel('Volume')
        ax2 = ax1.twinx()
        ax2.plot(es_data['Date'], es_data['Open_Interest'], color='red', marker='o', linewidth=2)
        ax2.set_ylabel('Open Interest', color='red')
        plt.tight_layout()
        plt.savefig(os.path.join(DAILY_DIR, f'chart1_es_conviction_{suffix}.png'))
        plt.close()

    # --- CHART 2: Silver (SI) ---
    si_data = df[df['Product'] == 'SILVER FUTURES'].copy()
    if not si_data.empty:
        fig, ax1 = plt.subplots()
        ax1.set_title(f'Silver (SI) Conviction {title_suffix}', fontsize=16, fontweight='bold')
        ax1.bar(si_data['Date'], si_data['Volume'], color='silver', alpha=0.8, label='Volume')
        ax1.set_ylabel('Volume')
        ax2 = ax1.twinx()
        ax2.plot(si_data['Date'], si_data['Open_Interest'], color='darkblue', marker='s', linewidth=2)
        ax2.set_ylabel('Open Interest', color='darkblue')
        plt.tight_layout()
        plt.savefig(os.path.join(DAILY_DIR, f'chart2_si_conviction_{suffix}.png'))
        plt.close()

    # --- CHART 3: Smart vs Dumb Money ---
    sil_data = df[df['Product'] == 'MICRO SILVER FUTURES'].copy()
    if len(si_data) > 0 and len(sil_data) > 0:
        si_oi_norm = si_data['Open_Interest'] / si_data['Open_Interest'].iloc[0] * 100
        sil_oi_norm = sil_data['Open_Interest'] / sil_data['Open_Interest'].iloc[0] * 100
        plt.figure()
        plt.title(f'Silver Divergence {title_suffix}', fontsize=16, fontweight='bold')
        plt.plot(si_data['Date'], si_oi_norm, label='Institutions (Standard)', color='darkblue', linewidth=3)
        plt.plot(sil_data['Date'], sil_oi_norm, label='Retail (Micro)', color='orange', linewidth=3, linestyle='--')
        plt.axhline(100, color='black', linestyle=':')
        plt.ylabel('OI Relative Growth (Base=100)')
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(DAILY_DIR, f'chart3_silver_divergence_{suffix}.png'))
        plt.close()

    # --- CHART 4: Put/Call Flow ---
    es_calls = df[df['Product'] == 'E-MINI S&P 500 CALL'].copy()
    es_puts = df[df['Product'] == 'E-MINI S&P 500 PUT'].copy()
    if len(es_calls) > 0 and len(es_puts) > 0:
        flow = pd.merge(es_calls[['Date', 'Volume']], es_puts[['Date', 'Volume']], on='Date', suffixes=('_Call', '_Put'))
        flow['PC_Ratio'] = flow['Volume_Put'] / flow['Volume_Call']
        fig, ax1 = plt.subplots()
        ax1.set_title(f'S&P 500 Put/Call Flow {title_suffix}', fontsize=16, fontweight='bold')
        x = np.arange(len(flow))
        ax1.bar(x - 0.2, flow['Volume_Call'], 0.4, label='Calls', color='green', alpha=0.6)
        ax1.bar(x + 0.2, flow['Volume_Put'], 0.4, label='Puts', color='red', alpha=0.6)
        ax1.set_xticks(x)
        ax1.set_xticklabels(flow['Date'].dt.strftime('%m-%d'), rotation=45)
        ax2 = ax1.twinx()
        ax2.plot(x, flow['PC_Ratio'], color='purple', marker='X', linewidth=2)
        ax2.axhline(1.0, color='black', linestyle='--')
        ax2.set_ylabel('Ratio', color='purple')
        plt.tight_layout()
        plt.savefig(os.path.join(DAILY_DIR, f'chart4_spy_options_flow_{suffix}.png'))
        plt.close()

    # --- CHART 5: 10Y Yields ---
    tn_data = df[df['Product'] == '10Y NOTE FUTURE'].copy()
    if len(tn_data) > 0:
        fig, ax1 = plt.subplots()
        ax1.set_title(f'Macro 10Y Note Yield Warning {title_suffix}', fontsize=16, fontweight='bold')
        ax1.bar(tn_data['Date'], tn_data['Volume'], color='darkorange', alpha=0.5)
        ax2 = ax1.twinx()
        ax2.plot(tn_data['Date'], tn_data['OI_Change'], color='teal', marker='^', linewidth=2)
        ax2.axhline(0, color='black')
        plt.tight_layout()
        plt.savefig(os.path.join(DAILY_DIR, f'chart5_macro_10y_yields_{suffix}.png'))
        plt.close()

    # --- CHART 6: COMEX Inventory (30d Line Version) ---
    if suffix == "30d":
        if inv_df is not None and not inv_df.empty:
            inv_df['Date'] = pd.to_datetime(inv_df['Date'])
            fig, ax1 = plt.subplots()
            ax1.set_title(f'COMEX Inventory Trend (30 Days)\nRegistered vs Eligible Silver Holdings', fontsize=16, fontweight='bold')
            ax1.plot(inv_df['Date'], inv_df['Eligible']/1e6, label='Eligible', color='silver', linewidth=3, marker='o')
            ax1.plot(inv_df['Date'], inv_df['Registered']/1e6, label='Registered', color='darkblue', linewidth=3, marker='s')
            from matplotlib.ticker import FuncFormatter
            ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{int(x)}M'))
            ax1.set_ylim(bottom=0)
            ax1.legend(loc='center right')
            plt.tight_layout()
            plt.savefig(os.path.join(DAILY_DIR, f'chart6_comex_inventory_{suffix}.png'))
            plt.close()

def generate_dashboard_charts(df, inventory_df, tactical_text=""):
    if df is None or df.empty: return
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')
    
    create_charts(df, "30d", "(30-Day Trend)", inventory_df)
    unique_dates = df['Date'].unique()
    create_charts(df[df['Date'].isin(unique_dates[-7:])].copy(), "7d", "(7-Day Momentum)", inventory_df)

    prices = fetch_market_prices()
    html_template = "volume_dashboard.html"
    
    if os.path.exists(html_template) and inventory_df is not None and not inventory_df.empty:
        with open(html_template, 'r') as f: html = f.read()

        def get_format(val, pfx=""):
            cls = "up" if val > 0 else "down" if val < 0 else ""
            fmt_str = f"{'+' if val >= 0 else ''}{pfx}{abs(val):,.2f}"
            return fmt_str, cls

        # ...existing price and vaults replacement logic...
        v, c = get_format(prices['SLV']['change'], "$")
        html = html.replace("{{SLV_PRICE}}", f"${prices['SLV']['price']:,.2f}")
        html = html.replace("{{SLV_CHANGE}}", v).replace("{{SLV_CLASS}}", c)
        slv_pct = (prices['SLV']['change'] / prices['SLV']['price'] * 100) if prices['SLV']['price'] else 0.0
        html = html.replace("{{SLV_PCT}}", f"{slv_pct:+.2f}%")

        v, c = get_format(prices['SIH26']['change'], "$")
        html = html.replace("{{SIH26_PRICE}}", f"${prices['SIH26']['price']:,.2f}")
        html = html.replace("{{SIH26_CHANGE}}", v).replace("{{SIH26_CLASS}}", c)
        sih26_pct = (prices['SIH26']['change'] / prices['SIH26']['price'] * 100) if prices['SIH26']['price'] else 0.0
        html = html.replace("{{SIH26_PCT}}", f"{sih26_pct:+.2f}%")

        v, c = get_format(prices['SPOT']['change'], "$")
        html = html.replace("{{SPOT_PRICE}}", f"${prices['SPOT']['price']:,.2f}")
        html = html.replace("{{SPOT_CHANGE}}", v).replace("{{SPOT_CLASS}}", c)
        spot_pct = (prices['SPOT']['change'] / prices['SPOT']['price'] * 100) if prices['SPOT']['price'] else 0.0
        html = html.replace("{{SPOT_PCT}}", f"{spot_pct:+.2f}%")

        v, c = get_format(prices['SHFE']['change'], "¥")
        arb = prices['SHFE']['usd_oz'] - prices['SPOT']['price']
        arb_str, arb_class = get_format(arb, "Arb: +$") 
        html = html.replace("{{SHFE_PRICE}}", f"¥{prices['SHFE']['price']:,.0f}")
        html = html.replace("{{SHFE_CHANGE}}", f"{v} <br> <span class='{arb_class}' style='font-size:0.8rem'>{arb_str}</span>")
        html = html.replace("{{SHFE_CLASS}}", c)
        shfe_pct = (prices['SHFE']['change'] / prices['SHFE']['price'] * 100) if prices['SHFE']['price'] else 0.0
        html = html.replace("{{SHFE_PCT}}", f"{shfe_pct:+.2f}%")

        inv = inventory_df.iloc[-1]
        html = html.replace("{{REG_OZ}}", f"{inv['Registered']/1e6:.1f}M oz")
        html = html.replace("{{ELIG_OZ}}", f"{inv['Eligible']/1e6:.1f}M oz")
        cv = inv['Total_Change']
        cv_fmt = f"{cv/1e6:+.1f}M oz" if abs(cv) >= 1e6 else f"{cv:+,.0f} oz"
        html = html.replace("{{DAILY_CHANGE}}", cv_fmt)
        html = html.replace("{{CHANGE_COLOR}}", "down" if cv < 0 else "up" if cv > 0 else "")
        html = html.replace("{{LAST_UPDATED}}", datetime.now().strftime("%I:%M %p"))

        # --- Inject Tactical Ruling Section ---
        if tactical_text:
            # Format as a dashboard card
            tactical_html = f'''
<div class="card" style="border-top: 3px solid var(--accent-blue); margin-top: 30px;">
  <h2 style="color: var(--accent-blue);">Tactical Ruling: Macro Debrief</h2>
  <pre style="font-family: 'Fira Mono', 'Consolas', 'Menlo', monospace; background: #181c20; color: #c5c6c7; padding: 18px; border-radius: 8px; font-size: 1.08rem; white-space: pre-wrap; margin: 0;">{tactical_text}</pre>
</div>
'''
            # Insert before </div> of grid-container (end of dashboard)
            html = html.replace('</div>\n</body>', tactical_html + '\n</div>\n</body>')
            print("✅ Tactical Ruling section injected into HTML dashboard.")

        with open(os.path.join(DAILY_DIR, "volume_dashboard.html"), 'w') as f: f.write(html)
        print("✅ Dashboard Ready.")

if __name__ == "__main__":
    generate_dashboard_charts()