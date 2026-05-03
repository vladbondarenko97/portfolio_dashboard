import os
from config import required_env
import csv
import math
import databento as db
import yfinance as yf
from datetime import datetime, timedelta, timezone
from scipy.stats import norm

# --- CONFIGURATION ---
from config import DATA_DIR, DATABENTO_API_KEY

# Create a dedicated ledger for institutional flow to keep macro data clean
LEDGER_CSV = os.path.join(DATA_DIR, "equities_darkpool_gex_ledger.csv")
TICKERS = ["SPY", "SLV"]

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize Databento
db_client = db.Historical(DATABENTO_API_KEY)

# --- THE BLACK-SCHOLES ENGINE ---
def calculate_gamma(S, K, T, r, sigma):
    """Calculates Options Gamma using the Black-Scholes formula."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    return gamma

# --- DARK POOL SCANNER ---
def get_dark_pool_profile(ticker):
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    available_end = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # T+1 Historical Barrier Fix
    if available_end.weekday() == 6: # Sunday Midnight UTC
        end_time = available_end - timedelta(days=1)
    elif available_end.weekday() == 0: # Monday Midnight UTC
        end_time = available_end - timedelta(days=2)
    else:
        end_time = available_end
        
    start_time = end_time - timedelta(days=1)
    
    try:
        data = db_client.timeseries.get_range(
            dataset='DBEQ.BASIC',
            schema='trades',       
            symbols=[ticker],
            start=start_time.isoformat(),
            end=end_time.isoformat(),
            limit=50000            
        )
        
        df = data.to_df()
        if df.empty:
            return None

        blocks = df[df['size'] >= 10000].copy()
        if blocks.empty:
            return None

        bullish_vol = int(blocks[blocks['side'] == 'A']['size'].sum())
        bearish_vol = int(blocks[blocks['side'] == 'B']['size'].sum())
        
        sentiment = "NEUTRAL"
        if bullish_vol > bearish_vol * 1.2: sentiment = "BULLISH"
        elif bearish_vol > bullish_vol * 1.2: sentiment = "BEARISH"

        return {
            "total_block_volume": int(blocks['size'].sum()),
            "total_notional_usd": float((blocks['price'] * blocks['size']).sum()),
            "largest_single_block": int(blocks['size'].max()),
            "vwap_price": float((blocks['price'] * blocks['size']).sum() / blocks['size'].sum()),
            "sentiment": sentiment,
            "bull_volume": bullish_vol,
            "bear_volume": bearish_vol
        }
    except Exception as e:
        print(f"⚠️ Dark Pool Error for {ticker}: {e}")
        return None

# --- GEX PROFILE SCANNER ---
def get_gex_profile(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # Safe spot price extraction
        history = ticker.history(period='1d')
        if history.empty:
            return None
        spot_price = history['Close'].iloc[-1]
        
        expirations = ticker.options
        if not expirations:
            return None
            
        target_exps = expirations[:3] 
        gex_by_strike = {}
        risk_free_rate = 0.05 
        
        for exp in target_exps:
            opt_chain = ticker.option_chain(exp)
            
            exp_date = datetime.strptime(exp, '%Y-%m-%d')
            days_to_exp = (exp_date - datetime.today()).days
            T = max(days_to_exp / 365.0, 0.001) 
            
            # Process Calls
            for _, row in opt_chain.calls.iterrows():
                strike, oi, iv = row['strike'], row['openInterest'], row['impliedVolatility']
                if oi > 0 and iv > 0.01:
                    gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                    gex_by_strike[strike] = gex_by_strike.get(strike, 0) + (gamma * oi * 100 * spot_price)

            # Process Puts
            for _, row in opt_chain.puts.iterrows():
                strike, oi, iv = row['strike'], row['openInterest'], row['impliedVolatility']
                if oi > 0 and iv > 0.01:
                    gamma = calculate_gamma(spot_price, strike, T, risk_free_rate, iv)
                    gex_by_strike[strike] = gex_by_strike.get(strike, 0) - (gamma * oi * 100 * spot_price)

        lower_bound = spot_price * 0.85
        upper_bound = spot_price * 1.15
        filtered_strikes = {k: v for k, v in gex_by_strike.items() if lower_bound <= k <= upper_bound}
        
        if not filtered_strikes:
            return None

        return {
            "spot_price": round(spot_price, 2),
            "call_wall": max(filtered_strikes, key=filtered_strikes.get),
            "put_wall": min(filtered_strikes, key=filtered_strikes.get),
            "zero_gamma_approx": round(spot_price, 2) # Placeholder approximation for the flip line
        }
    except Exception as e:
        print(f"⚠️ GEX Error for {ticker_symbol}: {e}")
        return None

# --- CSV LEDGER SYSTEM ---
def log_to_csv(filepath, date_str, ticker, dp_data, gex_data):
    file_exists = os.path.isfile(filepath)
    
    headers = [
        "Date", "Ticker", "Spot_Price", 
        "DP_Sentiment", "DP_Total_Vol", "DP_Notional_USD", "DP_Largest_Block", "DP_VWAP", "DP_Bull_Vol", "DP_Bear_Vol",
        "GEX_Call_Wall", "GEX_Put_Wall", "GEX_Zero_Gamma"
    ]
    
    # Handle missing data cleanly
    row = {
        "Date": date_str,
        "Ticker": ticker,
        "Spot_Price": gex_data['spot_price'] if gex_data else "N/A",
        "DP_Sentiment": dp_data['sentiment'] if dp_data else "N/A",
        "DP_Total_Vol": dp_data['total_block_volume'] if dp_data else "N/A",
        "DP_Notional_USD": dp_data['total_notional_usd'] if dp_data else "N/A",
        "DP_Largest_Block": dp_data['largest_single_block'] if dp_data else "N/A",
        "DP_VWAP": round(dp_data['vwap_price'], 2) if dp_data else "N/A",
        "DP_Bull_Vol": dp_data['bull_volume'] if dp_data else "N/A",
        "DP_Bear_Vol": dp_data['bear_volume'] if dp_data else "N/A",
        "GEX_Call_Wall": gex_data['call_wall'] if gex_data else "N/A",
        "GEX_Put_Wall": gex_data['put_wall'] if gex_data else "N/A",
        "GEX_Zero_Gamma": gex_data['zero_gamma_approx'] if gex_data else "N/A"
    }

    with open(filepath, mode='a', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def run_institutional_scan():
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    output = []
    output.append(f"\n========================================")
    output.append(f" 🦅 INSTITUTIONAL ENGINE SCANNER")
    output.append(f" {today_str}")
    output.append(f"========================================\n")

    for ticker in TICKERS:
        output.append(f"Scanning {ticker}...")
        dp_data = get_dark_pool_profile(ticker)
        gex_data = get_gex_profile(ticker)
        
        log_to_csv(LEDGER_CSV, today_str, ticker, dp_data, gex_data)
        
        # Terminal Output
        spot = gex_data['spot_price'] if gex_data else "UNAVAILABLE"
        output.append(f"\n[{ticker} OVERVIEW] - Spot: ${spot}")
        
        if dp_data:
            output.append(f"  Dark Pool Bias:   {dp_data['sentiment']} (VWAP: ${dp_data['vwap_price']:.2f})")
            output.append(f"  Total Block Vol:  {dp_data['total_block_volume']:,} shares")
        else:
            output.append("  Dark Pool Bias:   NO DATA / T+1 WAIT")
            
        if gex_data:
            output.append(f"  GEX Call Wall:    ${gex_data['call_wall']}")
            output.append(f"  GEX Put Wall:     ${gex_data['put_wall']}")
        else:
            output.append("  GEX Walls:        NO OPTIONS DATA")
            
        output.append("-" * 40)

    output.append(f"\n✅ Scan complete. Historical data appended to:")
    output.append(f"   {LEDGER_CSV}\n")
    return "\n".join(output)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print(run_institutional_scan())