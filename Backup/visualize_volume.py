import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
import sys

# --- CONFIGURATION ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")

# Catch the folder name passed from the bash script
if len(sys.argv) > 1:
    DAILY_DIR = sys.argv[1]
else:
    TODAY_STR = datetime.now().strftime("%b-%d-%y")
    DAILY_DIR = os.path.join(DATA_DIR, TODAY_STR)

INPUT_FILE = os.path.join(DAILY_DIR, "master_market_data.csv")

def generate_dashboard_charts():
    # 1. Load the data from your local CSV
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: Could not find {INPUT_FILE}. Run your parser script first!")
        return

    df = pd.read_csv(INPUT_FILE)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')

    # Set professional "Bloomberg Style" aesthetics
    sns.set_theme(style="darkgrid")
    plt.rcParams['figure.figsize'] = (14, 7)

    print(f"📊 Loading data from {INPUT_FILE}...")
    print(f"📈 Generating charts in {DATA_DIR}...")

    # --- CHART 1: S&P 500 Institutional Conviction (ES) ---
    es_data = df[df['Product'] == 'E-MINI S&P 500 FUTURE'].copy()
    fig, ax1 = plt.subplots()
    ax1.set_title('S&P 500 (ES) - Institutional Conviction (Volume vs OI)', fontsize=16, fontweight='bold')
    ax1.bar(es_data['Date'], es_data['Volume'], color='skyblue', alpha=0.5, label='Volume')
    ax1.set_ylabel('Volume')
    ax2 = ax1.twinx()
    ax2.plot(es_data['Date'], es_data['Open_Interest'], color='red', marker='o', linewidth=2, label='Open Interest')
    ax2.set_ylabel('Open Interest', color='red')
    plt.tight_layout()
    plt.savefig(os.path.join(DAILY_DIR, 'chart1_es_conviction.png'))
    plt.close()

    # --- CHART 2: Silver Institutional Conviction (SI) ---
    si_data = df[df['Product'] == 'SILVER FUTURES'].copy()
    fig, ax1 = plt.subplots()
    ax1.set_title('Silver (SI) - Institutional Conviction (Volume vs OI)', fontsize=16, fontweight='bold')
    ax1.bar(si_data['Date'], si_data['Volume'], color='silver', alpha=0.8, label='Volume')
    ax1.set_ylabel('Volume')
    ax2 = ax1.twinx()
    ax2.plot(si_data['Date'], si_data['Open_Interest'], color='darkblue', marker='s', linewidth=2, label='Open Interest')
    ax2.set_ylabel('Open Interest', color='darkblue')
    plt.tight_layout()
    plt.savefig(os.path.join(DAILY_DIR, 'chart2_si_conviction.png'))
    plt.close()

    # --- CHART 3: Smart Money vs. Dumb Money Divergence ---
    sil_data = df[df['Product'] == 'MICRO SILVER FUTURES'].copy()
    # Normalize to 100 to compare the percentage trend
    si_oi_norm = si_data['Open_Interest'] / si_data['Open_Interest'].iloc[0] * 100
    sil_oi_norm = sil_data['Open_Interest'] / sil_data['Open_Interest'].iloc[0] * 100

    plt.figure()
    plt.title('Silver: Smart Money (SI) vs Retail (SIL) Divergence', fontsize=16, fontweight='bold')
    plt.plot(si_data['Date'], si_oi_norm, label='Institutions (Standard)', color='darkblue', linewidth=3)
    plt.plot(sil_data['Date'], sil_oi_norm, label='Retail (Micro)', color='orange', linewidth=3, linestyle='--')
    plt.axhline(100, color='black', linestyle=':')
    plt.ylabel('OI Relative Growth (Base=100)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(DAILY_DIR, 'chart3_silver_divergence.png'))
    plt.close()

    # --- CHART 4: Put/Call Flow (S&P 500) ---
    es_calls = df[df['Product'] == 'E-MINI S&P 500 CALL'].copy()
    es_puts = df[df['Product'] == 'E-MINI S&P 500 PUT'].copy()
    options_flow = pd.merge(es_calls[['Date', 'Volume']], es_puts[['Date', 'Volume']], on='Date', suffixes=('_Call', '_Put'))
    options_flow['PC_Ratio'] = options_flow['Volume_Put'] / options_flow['Volume_Call']

    fig, ax1 = plt.subplots()
    ax1.set_title('S&P 500 (ES) Put/Call Volume & Ratio', fontsize=16, fontweight='bold')
    x = np.arange(len(options_flow))
    ax1.bar(x - 0.2, options_flow['Volume_Call'], 0.4, label='Calls', color='green', alpha=0.6)
    ax1.bar(x + 0.2, options_flow['Volume_Put'], 0.4, label='Puts', color='red', alpha=0.6)
    ax1.set_xticks(x)
    ax1.set_xticklabels(options_flow['Date'].dt.strftime('%m-%d'), rotation=45)
    ax2 = ax1.twinx()
    ax2.plot(x, options_flow['PC_Ratio'], color='purple', marker='X', linewidth=2, label='P/C Ratio')
    ax2.axhline(1.0, color='black', linestyle='--')
    ax2.set_ylabel('Ratio', color='purple')
    plt.tight_layout()
    plt.savefig(os.path.join(DAILY_DIR, 'chart4_spy_options_flow.png'))
    plt.close()

    # --- CHART 5: 10Y Note Yield Warning Signal ---
    tn_data = df[df['Product'] == '10Y NOTE FUTURE'].copy()
    fig, ax1 = plt.subplots()
    ax1.set_title('Macro: 10Y Note Volume & OI Change (Yield Warning)', fontsize=16, fontweight='bold')
    ax1.bar(tn_data['Date'], tn_data['Volume'], color='darkorange', alpha=0.5)
    ax1.set_ylabel('Bond Volume')
    ax2 = ax1.twinx()
    ax2.plot(tn_data['Date'], tn_data['OI_Change'], color='teal', marker='^', linewidth=2)
    ax2.axhline(0, color='black')
    ax2.set_ylabel('Daily OI Change', color='teal')
    plt.tight_layout()
    plt.savefig(os.path.join(DAILY_DIR, 'chart5_macro_10y_yields.png'))
    plt.close()

    print(f"✅ Dashboard updated. All 5 charts are now in your CME_Data folder.")

if __name__ == "__main__":
    generate_dashboard_charts()