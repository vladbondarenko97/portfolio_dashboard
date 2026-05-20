import os
import sys
import pandas as pd
import yfinance as yf

# Ensure config and core can be imported
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.sqlite_layer import replace_df

def backfill():
    print("Fetching 1 year of historical data for BTC, Silver, and Gold...")
    
    btc = yf.Ticker("BTC-USD").history(period="1y")
    sil = yf.Ticker("SI=F").history(period="1y")
    gld = yf.Ticker("GC=F").history(period="1y")
    
    # We only need the Close prices. Ensure timezones match by removing timezone info
    btc.index = btc.index.tz_localize(None).normalize()
    sil.index = sil.index.tz_localize(None).normalize()
    gld.index = gld.index.tz_localize(None).normalize()

    # Combine into a single dataframe
    df = pd.DataFrame(index=btc.index)
    df['BTC_Price'] = btc['Close']
    df['Silver_Price'] = sil['Close']
    df['Gold_Price'] = gld['Close']
    
    # Forward fill missing values (metals don't trade on weekends)
    df.ffill(inplace=True)
    
    # Drop rows where we have NaN (e.g. at the very start before the first metals print)
    df.dropna(inplace=True)
    
    # Calculate ratios (How many ounces it takes to buy 1 BTC)
    df['Silver_BTC_Ratio'] = df['BTC_Price'] / df['Silver_Price']
    df['Gold_BTC_Ratio'] = df['BTC_Price'] / df['Gold_Price']
    
    # Format dates
    df.reset_index(inplace=True)
    df.rename(columns={'index': 'Date', 'Date': 'Date'}, inplace=True)
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    
    print(f"Writing {len(df)} rows to SQLite...")
    replace_df('crypto_metrics_history', df)
    print("✅ Successfully backfilled 1 year of crypto and metals metrics to SQLite!")

if __name__ == "__main__":
    backfill()
