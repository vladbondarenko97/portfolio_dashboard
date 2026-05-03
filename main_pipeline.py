import os
import sys
from config import DATA_DIR
from download_volume import download_latest_cme_files
from update_inventory import update_silver_inventory
from parse_volume import parse_cme_files
from tactical_ruling import print_tactical_ruling
from dump_data import aggregate_data_to_text
from visualize_volume import generate_dashboard_charts

def run_pipeline():
    print("🚀 Starting Dual-Horizon CME Engine in-memory pipeline...")
    
    # 1. Download volume files
    print("\n--- PHASE 1: DOWNLOADING CME VOLUME ---")
    download_latest_cme_files(30)
    
    # 2. Update and get inventory dataframe
    print("\n--- PHASE 2: UPDATING COMEX INVENTORY ---")
    inventory_df = update_silver_inventory()
    
    # 3. Parse volume files to get volume dataframe
    print("\n--- PHASE 3: PARSING CME VOLUME ---")
    volume_df = parse_cme_files(30)
    
    # 4. Run Tactical Ruling (Macro Debrief)
    print("\n--- PHASE 4: TACTICAL RULING (MACRO) ---")
    tactical_xml = print_tactical_ruling(inventory_df)
    
    # 5. Dump data (aggregates all into a final file)
    print("\n--- PHASE 5: MASTER DATA DUMP ---")
    aggregate_data_to_text(volume_df, inventory_df, tactical_xml)
    
    # 6. Visualize (Generate HTML and charts)
    print("\n--- PHASE 6: DASHBOARD VISUALIZATION ---")
    generate_dashboard_charts(volume_df, inventory_df, tactical_xml)
    
    print("\n🎉 Pipeline Execution Complete!")

if __name__ == "__main__":
    run_pipeline()
