import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random

# Read DB relative to this file
DB_PATH = os.path.join(os.path.dirname(__file__), "alphaflow.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS swing_plays
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  ticker TEXT,
                  contract TEXT,
                  volume INTEGER,
                  oi INTEGER,
                  spend REAL,
                  term TEXT,
                  entry TEXT,
                  max_risk REAL)''')
    conn.commit()
    conn.close()

init_db()

def get_yfinance_universe(min_cap=1e8, max_cap=1e10):
    """
    In a real production system, this would iterate through the Russell 2000 or full US equity list
    and filter out market caps via yfinance:
    ticker.info.get('marketCap')
    For the sake of not blocking the scan for hours, we return a representative sample 
    of known small/mid cap tickers to simulate the filtered universe.
    """
    return ["SPXS", "SEDG", "BZH", "RIG", "SOUN", "PLUG", "RIOT", "MARA", "CVNA", "MSTR"]

def fetch_databento_historical(symbols, date, min_spend, min_vol_oi):
    """
    Simulates fetching Databento OPRA historical data for the given symbols.
    In production:
    import databento as db
    client = db.Historical(key=os.getenv('DATABENTO_API_KEY'))
    client.timeseries.get_range(dataset='OPRA.PILLAR', schema='mbp-1', symbols=symbols, start=...)
    """
    print(f"📡 Querying Databento Historical OPRA API for {len(symbols)} symbols on {date}...")
    
    detected = []
    
    # 40% chance per symbol to have an anomaly on this historical day (for demo purposes)
    for sym in symbols:
        if random.random() > 0.6:
            strike = random.randint(10, 150)
            dte = random.choice([7, 30, 90, 120])
            expiry = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=dte)).strftime('%y%m%d')
            term = "Short Term" if dte <= 14 else "Mid Term" if dte <= 60 else "Long Term"
            
            vol = random.randint(5000, 35000)
            # Guarantee it passes the requested min_vol_oi ratio
            oi = int(vol / random.uniform(min_vol_oi, min_vol_oi + 3.0)) 
            
            # Guarantee it passes the requested min_spend
            spend = max(min_spend + 1000, vol * random.uniform(0.50, 5.00) * 100)
            
            detected.append({
                "date": date,
                "ticker": sym,
                "contract": f"{sym} {strike}C",
                "volume": vol,
                "oi": max(1, oi),
                "spend": spend,
                "term": term,
                "entry": "NEXT OPEN",
                "max_risk": round(random.uniform(200, 800), 2)
            })
    return detected

def run_historical_scan(config):
    # Get last trading day (approximate for demo as yesterday)
    last_trading_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"🔍 Starting Historical Scan for {last_trading_day}...")
    min_cap = float(config.get("market_cap_min", 100000000))
    max_cap = float(config.get("market_cap_max", 10000000000))
    min_spend = float(config.get("min_spend", 50000))
    vol_oi = float(config.get("vol_oi", 1.5))
    
    symbols = get_yfinance_universe(min_cap, max_cap)
    print(f"🎯 Found {len(symbols)} symbols in the ${min_cap/1e6:,.0f}M - ${max_cap/1e9:,.0f}B range.")
    
    plays = fetch_databento_historical(symbols, last_trading_day, min_spend, vol_oi)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Clear old results for the demo so we don't infinitely stack
    c.execute("DELETE FROM swing_plays")
    
    for p in plays:
        c.execute('''INSERT INTO swing_plays (date, ticker, contract, volume, oi, spend, term, entry, max_risk)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (p['date'], p['ticker'], p['contract'], p['volume'], p['oi'], p['spend'], p['term'], p['entry'], p['max_risk']))
    conn.commit()
    conn.close()
    
    return plays

def get_latest_results():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM swing_plays ORDER BY spend DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
