import sqlite3
import pandas as pd
import os
import sys

# Ensure config can be imported if this is run standalone
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import DB_PATH, DATA_DIR

def get_connection():
    return sqlite3.connect(DB_PATH)

def append_row(table_name, row_dict):
    """
    Appends a single dictionary as a row to the specified SQLite table.
    If the table doesn't exist, it creates it with basic TEXT types.
    """
    df = pd.DataFrame([row_dict])
    with get_connection() as conn:
        df.to_sql(table_name, con=conn, if_exists='append', index=False)

def append_df(table_name, df):
    """
    Appends a pandas DataFrame to the specified SQLite table.
    """
    with get_connection() as conn:
        df.to_sql(table_name, con=conn, if_exists='append', index=False)

def replace_df(table_name, df):
    """
    Replaces a pandas DataFrame in the specified SQLite table.
    Useful for data that gets fully regenerated instead of appended.
    """
    with get_connection() as conn:
        df.to_sql(table_name, con=conn, if_exists='replace', index=False)

def init_historical_data():
    """
    One-time synchronization utility to read all existing CSV/Excel files
    in CME_Data and load them into SQLite to preserve historical data.
    """
    print(f"Starting one-time historical sync to {DB_PATH}...")
    import glob
    
    # 1. Single-file CSV ledgers
    ledgers = {
        "macro_master_ledger.csv": "macro_master_ledger",
        "equities_darkpool_gex_ledger.csv": "equities_darkpool_gex_ledger",
        "institutional_ledger.csv": "institutional_ledger",
        "physical_arbitrage_ledger.csv": "physical_arbitrage_ledger",
        "comex_inventory_history.csv": "comex_inventory_history"
    }
    
    for filename, table in ledgers.items():
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath)
                replace_df(table, df)
                print(f"Loaded {filename} into table '{table}' ({len(df)} rows)")
            except Exception as e:
                print(f"Failed to load {filename}: {e}")
                
    # 2. Time-series Excel files (daily_volume)
    daily_volume_files = glob.glob(os.path.join(DATA_DIR, "daily_volume_*.xlsx"))
    if daily_volume_files:
        all_dfs = []
        for f in daily_volume_files:
            try:
                df = pd.read_excel(f)
                basename = os.path.basename(f)
                date_str = basename.replace("daily_volume_", "").replace(".xlsx", "")
                df['source_date'] = date_str
                all_dfs.append(df)
            except Exception as e:
                print(f"Skipping {f}: {e}")
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            replace_df("daily_volume", combined)
            print(f"Combined {len(all_dfs)} daily volume files into table 'daily_volume' ({len(combined)} rows)")

    # 3. Silver stocks (silver_stocks_*.xls)
    silver_files = glob.glob(os.path.join(DATA_DIR, "silver_stocks_*.xls"))
    if silver_files:
        all_dfs = []
        for f in silver_files:
            try:
                # Based on get_latest_comex_inventory, we know to skip 7 rows
                df = pd.read_excel(f, skiprows=7)
                basename = os.path.basename(f)
                date_str = basename.replace("silver_stocks_", "").replace(".xls", "")
                df['source_date'] = date_str
                all_dfs.append(df)
            except Exception as e:
                print(f"Skipping {f}: {e}")
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            replace_df("silver_stocks", combined)
            print(f"Combined {len(all_dfs)} silver stock files into table 'silver_stocks' ({len(combined)} rows)")

    print("Historical sync complete! 🎉")

if __name__ == "__main__":
    init_historical_data()
