import pandas as pd
from flask import Flask, jsonify, render_template_string, Response, request, render_template
from flask_cors import CORS # Add this
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import requests
import warnings
import subprocess
import os
import re
import random
import math
import time
import databento as db
import numpy as np
from scipy.stats import norm
from playwright.sync_api import sync_playwright


PYTHON_BIN = "/usr/local/Caskroom/miniconda/base/bin/python3"
RUN_COMMAND = "/Users/vladhq/Desktop/Python2026/run_dashboard.command"

OPTIONS_SCRIPT = "/Users/vladhq/Desktop/Python2026/options_scanner.py"
EBAY_SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ebay.py'))

INVENTORY_CSV = "/Users/vladhq/Desktop/CME_Data/comex_inventory_history.csv"
LEDGER_CSV = "/Users/vladhq/Desktop/CME_Data/macro_master_ledger.csv"

# Suppress pandas FutureWarnings for clean terminal output
warnings.simplefilter(action='ignore', category=FutureWarning)

app = Flask(__name__)

# 1. Force HTML templates to reload instantly (disable to make faster)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# 2. Force CSS/JS to never cache (Bulletproof method, disable to make faster)
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


CORS(app) # This allows your JS chart to talk to your API without security errors

# --- CONFIGURATION ---
NTFY_URL = "https://ntfy.sh/vladhq_alerts"

# ==========================================
# 1. MATH & LOGIC FILTERS
# ==========================================
def is_out_of_the_money(opt_type, strike, underlying_price):
    """Deep ITM options are usually hedges. We want directional OTM bets."""
    if opt_type == 'call':
        return strike > underlying_price
    elif opt_type == 'put':
        return strike < underlying_price
    return False

def calculate_vol_oi_ratio(volume, open_interest):
    """Finds 'New Blood'. If Volume > OI, new positions are opening live."""
    if pd.isna(volume) or volume <= 0:
        return 0.0
    if pd.isna(open_interest) or open_interest == 0:
        return 999.0 # Brand new strike being swept
    return round(volume / open_interest, 2)

def calculate_premium_spent(volume, last_price):
    """Calculates the estimated dollar value of the sweep."""
    if pd.isna(volume) or pd.isna(last_price):
        return 0.0
    return volume * last_price * 100 # Options represent 100 shares

# ==========================================
# 2. DATA HARVESTING ENGINE
# ==========================================
def get_current_price(ticker_symbol):
    """Fetches the live underlying stock price."""
    ticker = yf.Ticker(ticker_symbol)
    todays_data = ticker.history(period='1d')
    if todays_data.empty:
        raise ValueError(f"Could not fetch live price for {ticker_symbol}.")
    return todays_data['Close'].iloc[0]

def get_chains(ticker_symbol, max_days_out=None):
    """Fetches options chains. If max_days_out is None, fetches EVERYTHING."""
    ticker = yf.Ticker(ticker_symbol)
    expirations = ticker.options
    if not expirations:
        return pd.DataFrame()

    today = datetime.now()
    valid_chains = []

    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        days_to_exp = (exp_date - today).days
        
        # Filter by days out if a limit is set
        if max_days_out is None or (0 <= days_to_exp <= max_days_out):
            try:
                chain = ticker.option_chain(exp)
                chain.calls['expiration'] = exp
                chain.calls['type'] = 'call'
                chain.puts['expiration'] = exp
                chain.puts['type'] = 'put'
                valid_chains.append(chain.calls)
                valid_chains.append(chain.puts)
            except Exception:
                continue

    if not valid_chains:
        return pd.DataFrame()
    return pd.concat(valid_chains, ignore_index=True)

# ==========================================
# 3. NOTIFICATION DISPATCHER
# ==========================================
def send_whale_alert(ticker, contract, time_context):
    """Pushes a high-priority alert to the iPhone."""
    emoji = "🔥 CALL" if contract['type'] == 'call' else "🩸 PUT"
    title = f"{ticker} {time_context} WHALE |"
    body = (
        f"${emoji}: \n",
        f"Strike: ${contract['strike']} | Exp: {contract['expiration']}\n"
        f"Volume: {contract['volume']:,} vs OI: {contract['open_interest']:,}\n"
        f"Vol/OI Ratio: {contract['vol_oi_ratio']}x\n"
        f"Est. Premium: ${contract['premium_spent']:,.2f}"
    )
    headers = {
        "Title": title,
        "Priority": "high",
        "Tags": "whale,rotating_light"
    }
    try:
        requests.post(NTFY_URL, data=body.encode('utf-8'), headers=headers)
        print(f"Alert sent for {contract['symbol']}")
    except Exception as e:
        print(f"Failed to send alert: {e}")

# ==========================================
# 4. STRATEGY EXECUTORS
# ==========================================
def execute_morning_hunt(ticker):
    """8:31 AM LOGIC: Short DTE, High Urgency, >$100k Premium"""
    print(f"Executing Morning Hunt for {ticker}...")
    current_price = get_current_price(ticker)
    df = get_chains(ticker, max_days_out=14)
    
    if df.empty: return []
    whales_caught = []

    for index, row in df.iterrows():
        # Grab all the standard and new data points
        opt_type = row['type']
        strike = row['strike']
        vol = row['volume']
        oi = row['openInterest']
        last_price = row['lastPrice']
        bid = row['bid']
        ask = row['ask']
        iv = row.get('impliedVolatility', 0.0) # Safe extraction

        if not is_out_of_the_money(opt_type, strike, current_price): continue
        
        ratio = calculate_vol_oi_ratio(vol, oi)
        if ratio < 1.5: continue
        
        premium = calculate_premium_spent(vol, last_price)
        if premium < 100000: continue

        # Build the expanded dictionary
        whale_data = {
            "symbol": row['contractSymbol'], 
            "type": opt_type, 
            "expiration": row['expiration'],
            "strike": strike, 
            "volume": int(vol), 
            "open_interest": int(oi),
            "vol_oi_ratio": ratio, 
            "premium_spent": premium,
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "iv": iv
        }
        whales_caught.append(whale_data)
        send_whale_alert(ticker, whale_data, "🌅 MORNING")

    return sorted(whales_caught, key=lambda x: x['premium_spent'], reverse=True)


def execute_evening_hunt(ticker):
    """2:00 PM LOGIC: All DTEs, Massive Blocks/Positioning, >$500k Premium"""
    print(f"Executing Evening Hunt for {ticker}...")
    current_price = get_current_price(ticker)
    df = get_chains(ticker, max_days_out=None) 
    
    if df.empty: return []
    whales_caught = []

    for index, row in df.iterrows():
        # Grab all the standard and new data points
        opt_type = row['type']
        strike = row['strike']
        vol = row['volume']
        oi = row['openInterest']
        last_price = row['lastPrice']
        bid = row['bid']
        ask = row['ask']
        iv = row.get('impliedVolatility', 0.0) # Safe extraction

        if not is_out_of_the_money(opt_type, strike, current_price): continue
        
        ratio = calculate_vol_oi_ratio(vol, oi)
        if ratio < 1.0: continue 
        
        premium = calculate_premium_spent(vol, last_price)
        if premium < 500000: continue 

        # Build the expanded dictionary
        whale_data = {
            "symbol": row['contractSymbol'], 
            "type": opt_type, 
            "expiration": row['expiration'],
            "strike": strike, 
            "volume": int(vol), 
            "open_interest": int(oi),
            "vol_oi_ratio": ratio, 
            "premium_spent": premium,
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "iv": iv
        }
        whales_caught.append(whale_data)
        send_whale_alert(ticker, whale_data, "🌆 EVENING")

    return sorted(whales_caught, key=lambda x: x['premium_spent'], reverse=True)

def execute_custom_hunt(ticker, min_vol_oi, min_premium, max_dte):
    """CUSTOM LOGIC: User-defined thresholds passed via URL"""
    print(f"Executing Custom Hunt for {ticker} | Vol/OI: {min_vol_oi} | Premium: {min_premium} | DTE: {max_dte}")
    current_price = get_current_price(ticker)
    df = get_chains(ticker, max_days_out=max_dte)
    
    if df.empty: return []
    whales_caught = []

    for index, row in df.iterrows():
        # Grab all the standard and new data points
        opt_type = row['type']
        strike = row['strike']
        vol = row['volume']
        oi = row['openInterest']
        last_price = row['lastPrice']
        bid = row['bid']
        ask = row['ask']
        iv = row.get('impliedVolatility', 0.0) # Safe extraction

        if not is_out_of_the_money(opt_type, strike, current_price): continue
        
        ratio = calculate_vol_oi_ratio(vol, oi)
        if ratio < min_vol_oi: continue 
        
        premium = calculate_premium_spent(vol, last_price)
        if premium < min_premium: continue 

        # Build the expanded dictionary
        whale_data = {
            "symbol": row['contractSymbol'], 
            "type": opt_type, 
            "expiration": row['expiration'],
            "strike": strike, 
            "volume": int(vol), 
            "open_interest": int(oi),
            "vol_oi_ratio": ratio, 
            "premium_spent": premium,
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "iv": iv
        }
        whales_caught.append(whale_data)
        send_whale_alert(ticker, whale_data, "🛠 CUSTOM")

    return sorted(whales_caught, key=lambda x: x['premium_spent'], reverse=True)

# ==========================================
# 5. FLASK API ROUTER
# ==========================================
def build_xml_response(ticker, strategy, whales):
    """Helper to convert the Python list of dicts into strict XML."""
    root = ET.Element("whale_hunt", ticker=ticker, strategy=strategy, whale_count=str(len(whales)))
    for w in whales:
        contract = ET.SubElement(root, "contract", symbol=w['symbol'], type=w['type'].upper(), expiration=w['expiration'])
        contract.set("strike", str(w['strike']))
        
        # New Pricing & Spread Data
        contract.set("last_price", f"${w['last_price']:.2f}")
        contract.set("bid", f"${w['bid']:.2f}")
        contract.set("ask", f"${w['ask']:.2f}")
        
        # Calculate the spread safely (avoiding negative or weird zero errors)
        spread = max(0.0, w['ask'] - w['bid'])
        contract.set("spread", f"${spread:.2f}")
        
        # Volume & Institutional Metrics
        contract.set("volume", str(w['volume']))
        contract.set("open_interest", str(w['open_interest']))
        contract.set("vol_oi_ratio", f"{w['vol_oi_ratio']}x")
        
        # IV and Total Capital
        contract.set("implied_volatility", f"{w['iv'] * 100:.2f}%")
        contract.set("premium_spent", f"${w['premium_spent']:,.2f}")

    xml_str = minidom.parseString(ET.tostring(root, encoding='utf-8')).toprettyxml(indent="  ")
    return Response(xml_str, mimetype='application/xml')

#--- BLACK-SCHOLES GAMMA CALCULATOR ---
def calculate_gamma(S, K, T, r, sigma):
    """
    S = Spot Price
    K = Strike Price
    T = Time to Expiration (in years)
    r = Risk-free rate
    sigma = Implied Volatility
    """
    # Prevent division by zero for expired options or zero vol
    if T <= 0 or sigma <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    
    # PDF of standard normal distribution
    nd1 = norm.pdf(d1) 
    
    gamma = nd1 / (S * sigma * np.sqrt(T))
    return gamma

@app.route('/api/gex')
def get_gex_profile():
    ticker_symbol = request.args.get('ticker', 'SPY').upper()
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        spot_price = ticker.info.get('regularMarketPrice') or ticker.history(period='1d')['Close'].iloc[-1]
        
        # Get all available expiration dates
        expirations = ticker.options
        if not expirations:
            return jsonify({"status": "error", "message": "No options data available."})
            
        # For a standard GEX profile, quants usually look at the front month or 0DTE.
        # We will grab the 3 closest expirations to build a thick profile.
        target_exps = expirations[:3] 
        
        gex_by_strike = {}
        risk_free_rate = 0.05 # Assuming ~5% risk-free rate
        
        for exp in target_exps:
            opt_chain = ticker.option_chain(exp)
            calls = opt_chain.calls
            puts = opt_chain.puts
            
            # Calculate Time to Expiration (T) in years
            # Approximation: (Expiration Date - Today) / 365
            import datetime
            exp_date = datetime.datetime.strptime(exp, '%Y-%m-%d')
            today = datetime.datetime.today()
            days_to_exp = (exp_date - today).days
            T = max(days_to_exp / 365.0, 0.001) # Minimum 1 day to prevent math errors
            
            # Process Calls (Positive Gamma)
            for _, row in calls.iterrows():
                strike = row['strike']
                oi = row['openInterest']
                iv = row['impliedVolatility']
                
                if oi > 0 and iv > 0.01:
                    gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                    # Dealer GEX Assumption: Dealers sell calls to retail, so they are short calls (negative gamma).
                    # Standard convention flips this for the chart: Calls = Positive GEX, Puts = Negative GEX
                    contract_gex = gamma * oi * 100 * spot_price
                    
                    gex_by_strike[strike] = gex_by_strike.get(strike, 0) + contract_gex

            # Process Puts (Negative Gamma)
            for _, row in puts.iterrows():
                strike = row['strike']
                oi = row['openInterest']
                iv = row['impliedVolatility']
                
                if oi > 0 and iv > 0.01:
                    gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                    contract_gex = gamma * oi * 100 * spot_price
                    
                    gex_by_strike[strike] = gex_by_strike.get(strike, 0) - contract_gex

        # Filter the strikes to only show a realistic window (e.g., +/- 10% from spot)
        lower_bound = spot_price * 0.90
        upper_bound = spot_price * 1.10
        
        filtered_strikes = {k: v for k, v in gex_by_strike.items() if lower_bound <= k <= upper_bound}
        
        # Sort strikes from lowest to highest
        sorted_strikes = sorted(filtered_strikes.keys())
        gamma_values = [filtered_strikes[k] for k in sorted_strikes]
        
        # Find the Walls
        call_wall_strike = max(filtered_strikes, key=filtered_strikes.get) if filtered_strikes else 0
        put_wall_strike = min(filtered_strikes, key=filtered_strikes.get) if filtered_strikes else 0
        
        # Approximate Zero Gamma (Flip point)
        # Find where the cumulative sum of gamma changes sign, or just the spot where it crosses 0
        zero_gamma = spot_price # Rough approximation for UI, real calc is complex root finding

        payload = {
            "spot": spot_price,
            "zeroGamma": zero_gamma,
            "callWall": call_wall_strike,
            "putWall": put_wall_strike,
            "strikes": sorted_strikes,
            "gamma": gamma_values
        }

        return jsonify({"status": "success", "data": payload})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# Initialize the Databento Client
# PRO TIP: In the future, put this in an environment variable!
DB_API_KEY = 'db-eLfjfMeAhtKf8QdqNWUFAhMGJAduq'
db_client = db.Historical(DB_API_KEY)

@app.route('/api/darkpool')
def get_dark_pool_profile():
    ticker = request.args.get('ticker', 'TSLA').upper()
    
    # --- THE WEEKEND DETECTOR FIX ---
    now = datetime.utcnow()
    
    # If today is Saturday (5) or Sunday (6), shift our 'end' back to Friday night
    if now.weekday() == 5:
        end_time = now - timedelta(days=1)
    elif now.weekday() == 6:
        end_time = now - timedelta(days=2)
    elif now.weekday() == 0 and now.hour < 14:
        # If it's Monday morning before market open, also look at Friday
        end_time = now - timedelta(days=3)
    else:
        end_time = now
        
    # Look back exactly 24 hours from our safe 'end_time'
    start_time = end_time - timedelta(days=1)
    
    try:
        # 1. THE QUERY: Fetch tick-level trades from the Consolidated Tape
        # Using DBEQ.MAX gives us all exchanges + 30 Dark Pools (ATS)
        data = db_client.timeseries.get_range(
            dataset='DBEQ.BASIC',
            schema='trades',       # We only want executed trades, not quotes yet
            symbols=[ticker],
            start=start_time.isoformat(),
            end=end_time.isoformat(),
            limit=50000            # Safety limit so we don't drain your credits
        )
        
        # Convert the raw binary stream into a Pandas DataFrame
        df = data.to_df()
        
        if df.empty:
            return jsonify({"status": "error", "message": "No trades found in the last 24h."})

        # 2. THE FILTER: Isolate the Whales
        # We only care about block trades (e.g., > 10,000 shares)
        # In a real environment, you can also filter by Databento's 'publisher_id' to isolate FINRA (Dark Pools)
        blocks = df[df['size'] >= 10000].copy()
        
        if blocks.empty:
            return jsonify({"status": "success", "message": "No institutional blocks detected.", "data": None})

        # 3. THE MATH: Calculate the Profile Metrics
        total_block_volume = int(blocks['size'].sum())
        total_notional = float((blocks['price'] * blocks['size']).sum())
        largest_block = int(blocks['size'].max())
        avg_block_price = float((blocks['price'] * blocks['size']).sum() / total_block_volume)

        # 4. THE SENTIMENT ENGINE (Bullish vs Bearish)
        # Databento's 'side' column tells us who crossed the spread:
        # 'A' = Aggressor hit the Ask (Bullish Buy)
        # 'B' = Aggressor hit the Bid (Bearish Sell)
        bullish_vol = int(blocks[blocks['side'] == 'A']['size'].sum())
        bearish_vol = int(blocks[blocks['side'] == 'B']['size'].sum())
        
        # Determine overall bias
        sentiment = "NEUTRAL"
        if bullish_vol > bearish_vol * 1.2: sentiment = "BULLISH"
        elif bearish_vol > bullish_vol * 1.2: sentiment = "BEARISH"

        # 5. THE PAYLOAD: Send clean data to your Javascript Terminal
        payload = {
            "ticker": ticker,
            "total_block_volume": total_block_volume,
            "total_notional_usd": total_notional,
            "largest_single_block": largest_block,
            "vwap_price": avg_block_price,
            "sentiment": {
                "bias": sentiment,
                "bull_volume": bullish_vol,
                "bear_volume": bearish_vol
            },
            "recent_prints": []
        }

        # Grab the 5 most recent massive prints for the UI list
        recent_trades = blocks.tail(5).sort_index(ascending=False)
        for index, row in recent_trades.iterrows():
            payload["recent_prints"].append({
                "time": index.strftime("%H:%M:%S"),
                "price": float(row['price']),
                "size": int(row['size']),
                "side": "BUY" if row['side'] == 'A' else "SELL" if row['side'] == 'B' else "UNK"
            })

        return jsonify({"status": "success", "data": payload})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- ENDPOINT: VMRI DATA PROXY ---
@app.route('/api/vmri_history')
def get_vmri_history():
    """Returns the time-series history of VMRI scores plus macro context."""
    try:
        if not os.path.exists(LEDGER_CSV):
            return jsonify({"error": "Ledger not found"}), 404
            
        df = pd.read_csv(LEDGER_CSV)
        
        # 1. THE FIX: Drop completely empty rows or rows missing a Datetime BEFORE parsing
        df = df.dropna(how='all')
        df = df.dropna(subset=['Datetime'])
        
        df['Datetime'] = pd.to_datetime(df['Datetime'], format='mixed')
        
        # Drop any dates that failed to parse (NaT)
        df = df.dropna(subset=['Datetime'])
        
        df = df.sort_values('Datetime').tail(500) # Last 500 records
        
        labels = df['Datetime'].dt.strftime('%Y-%m-%d %H:%M').tolist()
        
        # THE ULTIMATE LIST CLEANER
        def clean_list(lst):
            cleaned = []
            for val in lst:
                if pd.isna(val) or val in ["NaN", "nan", "None", ""]:
                    cleaned.append(None)
                else:
                    try:
                        f = float(val)
                        if math.isnan(f) or math.isinf(f):
                            cleaned.append(None)
                        else:
                            cleaned.append(f)
                    except (ValueError, TypeError):
                        cleaned.append(None)
            return cleaned
        
        data = {
            "labels": labels,
            "scores": clean_list(df['VMRI_Score'].tolist()),
            "context": {
                "dxy": clean_list(df['DXY'].tolist()),
                "yield": clean_list(df['10Y_Yield'].tolist()),
                "vix": clean_list(df['VIX'].tolist()),
                "gold": clean_list(df['Gold_Price'].tolist()),
                "gsr": clean_list(df['Gold_Silver_Ratio'].tolist()),
                "oas": clean_list(df['High_Yield_OAS'].tolist())
            }
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ENDPOINT: VMRI CHART VIEWER ---
@app.route('/vmri_chart')
def vmri_chart_page():
    """Serves a professional-grade interactive risk monitor."""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VMRI Systemic Risk Monitor</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: 'Courier New', monospace; background: #050505; color: #00ff00; padding: 10px; margin: 0; }
            .container { width: 95vw; margin: 20px auto; background: #000; padding: 20px; border: 1px solid #1a1a1a; border-radius: 4px; }
            h2 { text-align: center; color: #ff0000; letter-spacing: 3px; font-size: 20px; margin-bottom: 5px; }
            .subtitle { text-align: center; color: #666; font-size: 10px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🚨 VMRI SYSTEMIC RISK MONITOR 🚨</h2>
            <div class="subtitle">INTERACTIVE MACRO CROSS-ASSET LEDGER</div>
            <canvas id="vmriChart" height="120"></canvas>
        </div>

        <script>
            async function loadChart() {
                try {
                    const response = await fetch('/api/vmri_history');
                    const data = await response.json();

                    const ctx = document.getElementById('vmriChart').getContext('2d');
                    let gradient = ctx.createLinearGradient(0, 0, 0, 500);
                    gradient.addColorStop(0, 'rgba(255, 0, 0, 0.4)');
                    gradient.addColorStop(0.6, 'rgba(255, 165, 0, 0.1)');
                    gradient.addColorStop(1, 'rgba(0, 255, 0, 0.02)');

                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                label: 'VMRI',
                                data: data.scores,
                                borderColor: '#00ff00',
                                borderWidth: 2,
                                fill: true,
                                backgroundColor: gradient,
                                tension: 0.2,
                                pointRadius: 0,
                                pointHoverRadius: 6,
                                pointHoverBackgroundColor: '#ff0000',
                                pointHoverBorderWidth: 2
                            }]
                        },
                        options: {
                            responsive: true,
                            interaction: {
                                mode: 'index',
                                intersect: false, // Allows hover by just moving across X-axis
                            },
                            scales: {
                                y: { 
                                    min: 100, 
                                    grid: { color: '#111' }, 
                                    ticks: { color: '#444' } 
                                },
                                x: { display: false }
                            },
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    enabled: true,
                                    backgroundColor: 'rgba(10, 10, 10, 0.95)',
                                    titleFont: { size: 14, family: 'monospace' },
                                    titleColor: '#00ff00',
                                    bodyFont: { family: 'monospace' },
                                    borderColor: '#333',
                                    borderWidth: 1,
                                    displayColors: false,
                                    padding: 15,
                                    callbacks: {
                                        title: function(tooltipItems) {
                                            return "TIMESTAMP: " + tooltipItems[0].label;
                                        },
                                        label: function(context) {
                                            const i = context.dataIndex;
                                            const ctxData = data.context;
                                            
                                            // Format the tooltip with all CSV columns
                                            let label = [
                                                `SCORE:  ${context.parsed.y.toFixed(2)}`,
                                                `---------------------`
                                            ];
                                            
                                            if (ctxData.dxy[i])   label.push(`DXY:    ${ctxData.dxy[i].toFixed(2)}`);
                                            if (ctxData.yield[i]) label.push(`10Y:    ${ctxData.yield[i].toFixed(2)}%`);
                                            if (ctxData.vix[i])   label.push(`VIX:    ${ctxData.vix[i].toFixed(2)}`);
                                            if (ctxData.gold[i])  label.push(`GOLD:   $${ctxData.gold[i].toFixed(2)}`);
                                            if (ctxData.oas[i])   label.push(`SPREAD: ${ctxData.oas[i].toFixed(2)}`);
                                            
                                            return label;
                                        }
                                    }
                                }
                            }
                        }
                    });
                } catch (e) { console.error(e); }
            }
            loadChart();
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/api/war_room', methods=['GET', 'POST'])
def api_war_room():
    """
    The SecDB Lite Impact Engine.
    Accepts shift vectors for DXY, 10Y Yield, OAS, and VIX.
    Recalculates the VMRI and returns the hypothetical environment.
    """
    try:
        # Handle both GET (URL params) and POST (JSON body)
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args

        # 1. Parse Shift Vectors
        dxy_shift = float(data.get('dxy_shift', 0.0))
        tnx_shift = float(data.get('tnx_shift', 0.0))
        oas_shift = float(data.get('oas_shift', 0.0))
        vix_shift = float(data.get('vix_shift', 0.0))
        vix_shift_pct = float(data.get('vix_shift_pct', 0.0)) 

        # 2. Ingest the Latest Valid Live Environment
        df = pd.read_csv(LEDGER_CSV)
        # CRITICAL FIX: Drop completely empty rows that might be at the end of the CSV
        df = df.dropna(how='all') 
        latest = df.iloc[-1]

        # Helper to safely extract floats, with a secondary check to crawl up the CSV if needed
        def safe_float(col_name, fallback):
            val = latest.get(col_name)
            try:
                f = float(val)
                if pd.notna(f):
                    return f
            except:
                pass
                
            # If the absolute last row had a NaN for this specific column, 
            # crawl backwards up the CSV to find the last known good value.
            try:
                last_valid = df[col_name].dropna().iloc[-1]
                return float(last_valid)
            except:
                return fallback

        # Pull the real data (or crawl back to find it)
        base_dxy = safe_float('DXY', 100.0)
        base_tnx = safe_float('10Y_Yield', 4.0)
        base_oas = safe_float('High_Yield_OAS', 4.0)
        base_vix = safe_float('VIX', 20.0)
        base_vmri = safe_float('VMRI_Score', 200.0)

        # 3. Apply the Shift Vectors to create the Hypothetical Environment
        hypo_dxy = base_dxy + dxy_shift
        hypo_tnx = base_tnx + tnx_shift
        hypo_oas = base_oas + oas_shift
        
        # Calculate VIX shift 
        if vix_shift_pct != 0.0:
            hypo_vix = base_vix * (1 + (vix_shift_pct / 100.0))
        else:
            hypo_vix = base_vix + vix_shift

        # 4. The Math Engine: Recalculate VMRI
        base_stress = (hypo_dxy * hypo_tnx) / 1.61
        credit_multiplier = hypo_oas / 4.00
        vol_premium = hypo_vix / 20.00
        hypo_vmri = base_stress * credit_multiplier * vol_premium

        # 5. Determine the New Threat Tier
        if hypo_vmri < 150:
            tier = "LOW RISK (Complacent / Squeeze Danger)"
        elif 150 <= hypo_vmri < 250:
            tier = "MODERATE RISK (Standard Operating Environment)"
        elif 250 <= hypo_vmri < 350:
            tier = "ELEVATED RISK (Hedge Triggers Active)"
        else:
            tier = "SYSTEMIC THREAT (Crash Dynamics Active)"

        # 6. Calculate the Impact Delta
        vmri_delta = hypo_vmri - base_vmri
        vmri_delta_pct = (vmri_delta / base_vmri) * 100 if base_vmri != 0 else 0

        # 7. Construct the Output Payload
        payload = {
            "status": "success",
            "current": {
                "vmri": round(base_vmri, 2),
                "dxy": round(base_dxy, 2),
                "tnx": round(base_tnx, 2),
                "oas": round(base_oas, 2),
                "vix": round(base_vix, 2)
            },
            "hypothetical": {
                "vmri": round(hypo_vmri, 2),
                "tier": tier,
                "dxy": round(hypo_dxy, 2),
                "tnx": round(hypo_tnx, 2),
                "oas": round(hypo_oas, 2),
                "vix": round(hypo_vix, 2)
            },
            "impact": {
                "vmri_delta": round(vmri_delta, 2),
                "vmri_delta_pct": round(vmri_delta_pct, 2)
            }
        }

        return jsonify(payload)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/silver_eagle_prices', methods=['GET'])
def api_silver_eagle_prices():
    try:
        # Run the external ebay.py script
        output = subprocess.check_output(
            [PYTHON_BIN, EBAY_SCRIPT_PATH], 
            text=True, 
            timeout=120 # Playwright takes time, so give it a 2-minute timeout
        )
        
        # The script prints pure XML to stdout, so we just return it
        return Response(output, mimetype='application/xml')

    except subprocess.TimeoutExpired:
        return Response("<error>Scrape timed out. eBay might be blocking connections.</error>", mimetype='application/xml', status=504)
    except subprocess.CalledProcessError as e:
        return Response(f"<error>Script crashed: {e.output}</error>", mimetype='application/xml', status=500)
    except Exception as e:
        return Response(f"<error>Server error: {str(e)}</error>", mimetype='application/xml', status=500)

# --- ENDPOINT 1: THE DATA PROXY ---
@app.route('/api/inventory_data')
def get_inventory_data():
    """Reads the CSV and returns JSON for the JS Chart."""
    try:
        if not os.path.exists(INVENTORY_CSV):
            return jsonify({"error": "CSV not found"}), 404
            
        # Read CSV and ensure dates are sorted
        df = pd.read_csv(INVENTORY_CSV)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        # Convert to dictionary format for JSON
        data = {
            "labels": df['Date'].dt.strftime('%Y-%m-%d').tolist(),
            "registered": df['Registered'].tolist(),
            "eligible": df['Eligible'].tolist(),
            "total": df['Total'].tolist()
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# --- ENDPOINT 2: THE DASHBOARD VIEWER ---
@app.route('/inventory_chart')
def inventory_chart_page():
    """Serves a single-page HTML dashboard optimized for iFrame embedding."""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>COMEX Inventory Live Chart</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            /* OPTIMIZED FOR TERMINAL IFRAME */
            body { font-family: sans-serif; background: transparent; color: #eee; margin: 0; padding: 10px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }
            .container { flex: 1; display: flex; flex-direction: column; background: #1e1e1e; padding: 15px; border-radius: 4px; border: 1px solid #27272a; }
            h2 { text-align: center; color: #ffcc00; font-size: 14px; margin: 0 0 10px 0; font-weight: bold; letter-spacing: 1px; }
            .stats { display: flex; justify-content: space-around; margin-bottom: 10px; font-weight: bold; font-size: 11px; }
            .chart-wrapper { flex: 1; position: relative; min-height: 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🏦 COMEX PHYSICAL INVENTORY HISTORY</h2>
            <div class="stats" id="currentStats">Loading latest data...</div>
            <div class="chart-wrapper">
                <canvas id="inventoryChart"></canvas>
            </div>
        </div>

        <script>
            async function loadChart() {
                const response = await fetch('/api/inventory_data');
                const data = await response.json();

                // Update Stats Header
                const lastIdx = data.labels.length - 1;
                document.getElementById('currentStats').innerHTML = `
                    <span>Total: ${(data.total[lastIdx]/1e6).toFixed(2)}M oz</span>
                    <span style="color: #ff4444">Registered: ${(data.registered[lastIdx]/1e6).toFixed(2)}M oz</span>
                    <span style="color: #44ff44">Eligible: ${(data.eligible[lastIdx]/1e6).toFixed(2)}M oz</span>
                `;

                const ctx = document.getElementById('inventoryChart').getContext('2d');
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [
                            {
                                label: 'Registered (Sellable)',
                                data: data.registered,
                                borderColor: '#ff4444',
                                backgroundColor: 'rgba(255, 68, 68, 0.1)',
                                fill: true,
                                tension: 0.3,
                                pointRadius: 1
                            },
                            {
                                label: 'Eligible (Vaulted)',
                                data: data.eligible,
                                borderColor: '#44ff44',
                                tension: 0.3,
                                pointRadius: 1
                            },
                            {
                                label: 'Total Inventory',
                                data: data.total,
                                borderColor: '#ffcc00',
                                borderDash: [5, 5],
                                tension: 0.3,
                                pointRadius: 1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false, // <--- THE CRITICAL FIX
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        plugins: {
                            legend: { labels: { color: '#eee', boxWidth: 12, font: {size: 10} } }
                        },
                        scales: {
                            y: { 
                                ticks: { color: '#aaa', font: {size: 10}, callback: (v) => (v/1e6).toFixed(0) + 'M' },
                                grid: { color: '#333' }
                            },
                            x: { 
                                ticks: { color: '#aaa', font: {size: 10}, maxTicksLimit: 10 },
                                grid: { display: false }
                            }
                        }
                    }
                });
            }
            loadChart();
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/api/morning', methods=['GET'])
def api_morning():
    ticker = request.args.get('ticker', 'SPY').upper()
    try:
        # Run the scanner script as a subprocess
        # We use a timeout so it doesn't hang the UI forever
        output = subprocess.check_output(
            [PYTHON_BIN, OPTIONS_SCRIPT, ticker, "morning"], 
            text=True, 
            timeout=30
        )
        return jsonify({"status": "success", "ticker": ticker, "data": output})
    except subprocess.CalledProcessError as e:
        # If the script crashes, we return the error as JSON
        return jsonify({
            "status": "error", 
            "message": "Scanner script failed. It might be due to weekend data gaps.",
            "details": str(e.output if hasattr(e, 'output') else e)
        }), 200 # We return 200 so the UI doesn't trigger a browser-level 500 error
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/evening', methods=['GET'])
def api_evening():
    ticker = request.args.get('ticker', 'SPY').upper()
    try:
        # standardizing to use the subprocess scanner logic
        output = subprocess.check_output(
            [PYTHON_BIN, OPTIONS_SCRIPT, ticker, "evening"], 
            text=True, 
            timeout=30
        )
        return jsonify({"status": "success", "ticker": ticker, "data": output})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

# --- HELPER: NATIVE XML WHALE HUNT ---
def execute_xml_whale_hunt(ticker, min_vol_oi=1.0, max_dte=30, strategy="CUSTOM_HUNT"):
    """Fetches option chains and returns a structured XML object."""
    root = ET.Element("whale_hunt", ticker=ticker.upper(), strategy=strategy)
    
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            root.set("error", "No options found")
            return root

        today = datetime.now()
        whale_list = []

        # Iterate through expirations
        for exp in exps:
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days_to_exp = (exp_date - today).days
            
            # Apply Max DTE filter
            if max_dte and days_to_exp > int(max_dte):
                continue

            opt = tk.option_chain(exp)
            # Combine calls and puts into one list for processing
            for df, label in [(opt.calls, "CALL"), (opt.puts, "PUT")]:
                if df.empty: continue
                
                # Calculate metrics
                df['premium_spent'] = df['volume'] * df['lastPrice'] * 100
                df['vol_oi_ratio'] = df['volume'] / df['openInterest'].replace(0, 1)
                df['spread'] = df['ask'] - df['bid']

                # Filter: Vol/OI ratio (default >= 1.0)
                # We also add a basic premium floor ($100k) to keep the XML clean
                mask = (df['vol_oi_ratio'] >= float(min_vol_oi)) & (df['premium_spent'] >= 100000)
                whales = df[mask].copy()

                for _, row in whales.iterrows():
                    whale_list.append({
                        "symbol": row['contractSymbol'],
                        "type": label,
                        "expiration": exp,
                        "strike": str(row['strike']),
                        "last_price": f"${row['lastPrice']:.2f}",
                        "bid": f"${row['bid']:.2f}",
                        "ask": f"${row['ask']:.2f}",
                        "spread": f"${row['spread']:.2f}",
                        "volume": str(int(row['volume'])),
                        "open_interest": str(int(row['openInterest'])),
                        "vol_oi_ratio": f"{row['vol_oi_ratio']:.2f}x",
                        "implied_volatility": f"{row['impliedVolatility']*100:.2f}%",
                        "premium_spent": f"${row['premium_spent']:,.2f}",
                        "raw_premium": row['premium_spent'] # For sorting
                    })

        # Sort all found whales by premium spent (Highest first)
        whale_list.sort(key=lambda x: x['raw_premium'], reverse=True)
        root.set("whale_count", str(len(whale_list)))

        # Build the XML tree
        for w in whale_list:
            contract = ET.SubElement(root, "contract")
            for attr in ['symbol', 'type', 'expiration', 'strike', 'last_price', 
                         'bid', 'ask', 'spread', 'volume', 'open_interest', 
                         'vol_oi_ratio', 'implied_volatility', 'premium_spent']:
                contract.set(attr, w[attr])

    except Exception as e:
        root.set("error", str(e))

    return root

# --- THE ROUTE ---
@app.route('/api/custom', methods=['GET'])
def api_custom():
    ticker = request.args.get('ticker', 'SPY').upper()
    try:
        # 1. Parse Parameters
        min_vol_oi = float(request.args.get('min_vol_oi', 1.0))
        max_dte = request.args.get('max_dte', 365) # Default to 1 year if not set

        # 2. Execute the hunt
        xml_root = execute_xml_whale_hunt(ticker, min_vol_oi, max_dte)
        
        # 3. Convert to string and return as XML mimetype
        from xml.dom import minidom
        raw_xml = ET.tostring(xml_root, encoding='utf-8')
        pretty_xml = minidom.parseString(raw_xml).toprettyxml(indent="  ")
        
        return Response(pretty_xml, mimetype='application/xml')

    except Exception as e:
        return Response(f"<error>{str(e)}</error>", mimetype='application/xml', status=500)

@app.route('/', methods=['GET'])
def serve_terminal():
    """Serves the VladHQ Market Terminal UI."""
    return render_template('terminal.html')
    
@app.route('/help', methods=['GET'])
def api_help():
    """Outputs the complete API documentation in XML format."""
    help_xml = """<?xml version="1.0" ?>
<api_documentation>
  <endpoint path="/api/morning">
    <description>8:31 AM LOGIC: Hunts for urgent, short-term directional momentum.</description>
    <defaults max_dte="14 days" min_vol_oi="1.5x" min_premium="$100,000" />
    <parameters>
      <param name="ticker" required="true" type="string" example="SPY" />
    </parameters>
  </endpoint>
  
  <endpoint path="/api/evening">
    <description>2:00 PM LOGIC: Hunts for massive structural positioning and earnings bets.</description>
    <defaults max_dte="ALL" min_vol_oi="1.0x" min_premium="$500,000" />
    <parameters>
      <param name="ticker" required="true" type="string" example="NVDA" />
    </parameters>
  </endpoint>
  
  <endpoint path="/api/custom">
    <description>CUSTOM LOGIC: Dynamic scanner allowing user-defined overrides.</description>
    <parameters>
      <param name="ticker" required="true" type="string" example="TSLA" />
      <param name="min_vol_oi" required="false" type="float" default="1.0" example="3.5" description="Minimum Volume to Open Interest ratio" />
      <param name="min_premium" required="false" type="float" default="100000" example="1000000" description="Minimum estimated dollars spent" />
      <param name="max_dte" required="false" type="int" default="None" example="5" description="Maximum days to expiration (Leave blank for ALL)" />
    </parameters>
  </endpoint>

  <endpoint path="/run">
    <description>SYSTEM: Triggers the local run_dashboard.command script on the Mac and returns the execution timestamp.</description>
    <parameters />
  </endpoint>

  <endpoint path="/dump">
    <description>DATA: Automatically locates the most recent CME_Data folder and dumps the tactical ruling and volume dashboard text files.</description>
    <parameters />
  </endpoint>

  <endpoint path="/vmri">
    <description>MACRO: Extracts the latest Vlad Macro Risk Index (VMRI) score, including live calculations, formulas, and the mechanics breakdown from the latest tactical ruling.</description>
    <parameters />
  </endpoint>

  <endpoint path="/api/inventory_data">
    <description>DATA PROXY: Reads the master COMEX inventory history CSV and returns a JSON payload of Registered, Eligible, and Total volumes for time-series analysis.</description>
    <parameters />
  </endpoint>

  <endpoint path="/inventory_chart">
    <description>VISUAL: Serves a full-screen, high-contrast interactive dashboard using Chart.js to visualize physical COMEX silver inventory trends and vault drains.</description>
    <parameters />
  </endpoint>
</api_documentation>

  <endpoint path="/api/vmri_history">
    <description>HISTORICAL: Dumps the last 500 records from the macro ledger as JSON for external analysis.</description>
    <parameters />
  </endpoint>

  <endpoint path="/vmri_chart">
    <description>VISUAL: A "Mannarino-Style" historical trend chart for the VMRI. Shows risk escalation over time with color-coded threat zones.</description>
    <parameters />
  </endpoint>"""
    
    return Response(help_xml, mimetype='application/xml')

@app.route('/run', methods=['GET'])
def run_dashboard():
    """Executes the local dashboard command script and returns the exact timestamp."""
    # os.path.expanduser safely translates the "~" into "/Users/vladhq"
    script_path = os.path.expanduser("~/Desktop/Python2026/run_dashboard.command")
    
    # Verify the file actually exists before trying to run it
    if not os.path.exists(script_path):
        return Response("<error>Script not found at specified path.</error>", mimetype='application/xml', status=404)

    try:
        # Run the script. capture_output=True hides the terminal spam from the Flask console.
        # check=True forces Python to throw an error if the bash script fails or crashes.
        subprocess.run(["bash", script_path], check=True, capture_output=True, text=True)
        
        # Grab the exact time down to the second
        exact_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Build the XML success response
        root = ET.Element("execution_result", status="SUCCESS", timestamp=exact_time)
        msg = ET.SubElement(root, "message")
        msg.text = "Dashboard run initiated and completed successfully."
        
        xml_str = minidom.parseString(ET.tostring(root, encoding='utf-8')).toprettyxml(indent="  ")
        return Response(xml_str, mimetype='application/xml')

    except subprocess.CalledProcessError as e:
        # If the bash script crashes, this catches it and outputs the actual bash error
        return Response(f"<error>Script crashed during execution: {e.stderr}</error>", mimetype='application/xml', status=500)
    except Exception as e:
        return Response(f"<error>System Error: {str(e)}</error>", mimetype='application/xml', status=500)

@app.route('/api/dump', methods=['GET'])
@app.route('/dump', methods=['GET'])
def dump_data():
    """Finds the most recent CME_Data folder and intelligently merges XML files."""
    base_dir = os.path.expanduser("~/Desktop/CME_Data/")
    
    if not os.path.exists(base_dir):
        return Response("<error>CME_Data directory not found.</error>", mimetype='application/xml', status=404)

    # 1. Locate the latest folder
    subdirs = [os.path.join(base_dir, d) for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    if not subdirs:
        return Response("<error>No folders found.</error>", mimetype='application/xml', status=404)
    subdirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_folder = subdirs[0]

    # 2. Setup paths
    tactical_path = os.path.join(latest_folder, "tactical_ruling.txt")
    volume_path = os.path.join(latest_folder, "volume_dashboard.txt")

    # 3. Create Master Container
    root = ET.Element("cme_data_dump", source_folder=os.path.basename(latest_folder), timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Helper to parse and strip headers
    def get_parsed_xml(path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                clean = re.sub(r'<\?xml[^>]*\?>', '', content).strip()
                try:
                    return ET.fromstring(clean)
                except: return None
        return None

    # 4. INTELLECTUALLY MERGE
    tac_xml = get_parsed_xml(tactical_path)
    vol_xml = get_parsed_xml(volume_path)

    # If the tactical ruling exists standalone, add it first
    if tac_xml is not None:
        root.append(tac_xml)

    if vol_xml is not None:
        # CHECK: Is there a redundant tactical ruling inside the dashboard?
        # If so, remove it from the dashboard block so we don't have double data
        redundant_node = vol_xml.find("tactical_ruling")
        if redundant_node is not None and tac_xml is not None:
            vol_xml.remove(redundant_node)
            
        root.append(vol_xml)

    # 5. Generate Pretty Output
    raw_xml = ET.tostring(root, encoding='utf-8')
    xml_str = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    
    # Remove empty lines for a tighter output
    xml_str = os.linesep.join([s for s in xml_str.splitlines() if s.strip()])

    return Response(xml_str, mimetype='application/xml')

@app.route('/vmri', methods=['GET'])
def get_vmri():
    """Extracts the latest VMRI score and outputs it with full documentation and formulas."""
    base_dir = os.path.expanduser("~/Desktop/CME_Data/")
    
    if not os.path.exists(base_dir):
        return Response("<error>CME_Data directory not found.</error>", mimetype='application/xml', status=404)

    # Find the newest folder
    subdirs = [os.path.join(base_dir, d) for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    if not subdirs:
        return Response("<error>No daily folders found.</error>", mimetype='application/xml', status=404)

    subdirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    latest_folder = None
    tactical_content = ""

    # Hunt for the tactical ruling file
    for folder in subdirs:
        tactical_path = os.path.join(folder, "tactical_ruling.txt")
        if os.path.exists(tactical_path):
            latest_folder = folder
            with open(tactical_path, 'r', encoding='utf-8') as f:
                tactical_content = f.read()
            break

    if not tactical_content:
        return Response("<error>tactical_ruling.txt not found in recent folders.</error>", mimetype='application/xml', status=404)

    clean_content = re.sub(r'<\?xml[^>]*\?>', '', tactical_content).strip()
    
    try:
        tactical_tree = ET.fromstring(clean_content)
        vmri_node = tactical_tree.find(".//VLAD_MACRO_RISK_INDEX")
        
        if vmri_node is None:
            return Response("<error>VMRI data not found inside the latest tactical ruling.</error>", mimetype='application/xml', status=404)

        root = ET.Element("vmri_report", timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), source_folder=os.path.basename(latest_folder))
        
        # 1. Attach Live Data
        live_data = ET.SubElement(root, "live_calculation")
        live_data.append(vmri_node)

        # 2. Attach Top-Level Formula
        formula_node = ET.SubElement(root, "master_formula")
        formula_node.text = "VMRI Score = Base Stress * Credit Multiplier * Volatility Premium"
        
        # 3. Attach Documentation
        doc_node = ET.SubElement(root, "documentation")
        
        desc = ET.SubElement(doc_node, "description")
        desc.text = "The Vlad Macro Risk Index (VMRI) aggregates fixed income stress, credit spreads, and equity volatility into a single numerical threat level to dictate portfolio hedging aggression."
        
        # --- NEW: Mechanics Breakdown with Formulas ---
        mechanics_doc = ET.SubElement(doc_node, "mechanics_breakdown")
        
        # Base Stress
        bs = ET.SubElement(mechanics_doc, "metric", name="Base Stress")
        bs_desc = ET.SubElement(bs, "description")
        bs_desc.text = "The foundational risk score derived from interest rate volatility, 10-Year Treasury yields, and systemic liquidity."
        bs_form = ET.SubElement(bs, "formula")
        bs_form.text = "(DXY * 1.5) + (10Y Yield * 15) + (150 - ZN Futures) + (Reverse Repo * 10)"
        
        # Credit Multiplier
        cm = ET.SubElement(mechanics_doc, "metric", name="Credit Multiplier")
        cm_desc = ET.SubElement(cm, "description")
        cm_desc.text = "A scaling factor based on High Yield OAS spreads. Values < 1.0 mean credit is healthy and dampens risk. Values > 1.0 indicate widening credit spreads, amplifying the systemic threat."
        cm_form = ET.SubElement(cm, "formula")
        cm_form.text = "Current HY OAS / 4.00"
        cm_base = ET.SubElement(cm, "baseline")
        cm_base.text = "4.00%"
        
        # Volatility Premium
        vp = ET.SubElement(mechanics_doc, "metric", name="Volatility Premium")
        vp_desc = ET.SubElement(vp, "description")
        vp_desc.text = "An accelerator based on equity derivatives (VIX). Values > 1.0 mean options markets are pricing in severe near-term turbulence, driving up the final score."
        vp_form = ET.SubElement(vp, "formula")
        vp_form.text = "Current VIX / 20.00"
        vp_base = ET.SubElement(vp, "baseline")
        vp_base.text = "20.00"
        
        # Ranges
        ranges = ET.SubElement(doc_node, "ranges")
        ET.SubElement(ranges, "level", range="0 - 150", status="RISK ON", action="Maximize long exposure. Volatility is suppressed.")
        ET.SubElement(ranges, "level", range="150 - 250", status="BASELINE", action="Normal market conditions. Standard position sizing.")
        ET.SubElement(ranges, "level", range="250 - 350", status="ELEVATED RISK", action="Hedge triggers active. Reduce beta, increase cash.")
        ET.SubElement(ranges, "level", range="350+", status="SEVERE STRESS", action="Liquidity event probable. Maximum defensive posture.")

        # Generate pretty XML
        xml_str = minidom.parseString(ET.tostring(root, encoding='utf-8')).toprettyxml(indent="  ")
        xml_str = os.linesep.join([s for s in xml_str.splitlines() if s.strip()]) 

        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        return Response(f"<error>Failed to parse VMRI data: {str(e)}</error>", mimetype='application/xml', status=500)

@app.route('/api/macro_news', methods=['GET'])
def api_macro_news():
    """Fetches general macroeconomic news via public RSS without an API key."""
    try:
        # Switched to Yahoo Finance (Much more scraper-friendly than CNBC)
        rss_url = "https://finance.yahoo.com/news/rss"
        
        # A more robust set of headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            return Response(f"<error>Failed to fetch feed. HTTP Status: {response.status_code}</error>", mimetype='application/xml', status=502)
            
        # Parse the XML feed
        feed_tree = ET.fromstring(response.content)
        items = feed_tree.findall(".//item")[:10] # Grab top 10 headlines
        
        # Build our custom XML tree
        root = ET.Element("macro_news", timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), source="Yahoo_Finance")
        
        for item in items:
            title = item.findtext("title", "No Title")
            pub_date = item.findtext("pubDate", "Unknown Date")
            link = item.findtext("link", "No Link")
            
            article = ET.SubElement(root, "article")
            article.set("published", pub_date.replace(" GMT", "").replace(" +0000", ""))
            article.set("title", title.strip())
            article.set("link", link.strip())
            
        xml_str = minidom.parseString(ET.tostring(root, encoding='utf-8')).toprettyxml(indent="  ")
        xml_str = os.linesep.join([s for s in xml_str.splitlines() if s.strip()]) # Clean blank lines
        
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        return Response(f"<error>System Error: {str(e)}</error>", mimetype='application/xml', status=500)

if __name__ == "__main__":
    # Bound to Port 8080 as requested
    app.run(host='0.0.0.0', port=8080)