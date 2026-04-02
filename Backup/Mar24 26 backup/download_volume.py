import os
import time
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError
from playwright_stealth import Stealth

# --- CONFIGURATION ---
LOGIN_URL = "https://login.cmegroup.com/sso/accountstatus/showAuth.action"
STATIC_LATEST_URL = "https://www.cmegroup.com/ftp/daily_volume/daily_volume.xlsx"

USERNAME = "i@vlad.yt"
PASSWORD = "Veelad1337$$$"

# Saves to a folder named 'CME_Data' on your Mac's Desktop
SAVE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
STATE_FILE = os.path.join(SAVE_DIR, "state.json")

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def download_latest_cme_files(num_files_to_get=30):
    clear_terminal()
    print(f"CME VOLUME DOWNLOADER V4.0 (30-DAY / MONTHLY ARCHIVE)")
    print("=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=\n")

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, 
            args=[
                '--disable-blink-features=AutomationControlled', 
                '--disable-http2', 
                '--start-maximized'
            ]
        )
        
        context_args = {
            "user_agent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            "viewport": {'width': 1920, 'height': 1080},
            "accept_downloads": True,
            "timezone_id": "America/Chicago",
            "geolocation": {"latitude": 38.6270, "longitude": -90.1994},
            "permissions": ["geolocation"]
        }

        if os.path.exists(STATE_FILE):
            print("🟢 Found saved session (state.json). Loading cookies...\n")
            context_args["storage_state"] = STATE_FILE

        context = browser.new_context(**context_args)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        # --- LOGIN CHECK ---
        if not os.path.exists(STATE_FILE):
            print("🟡 No saved session found. Navigating to Login Page...")
            page.goto(LOGIN_URL)
            print("Typing credentials...")
            page.locator('input[type="text"], input[type="email"]').first.type(USERNAME, delay=100)
            page.locator('input[type="password"]').first.type(PASSWORD, delay=100)
            page.locator('button[type="submit"], input[type="submit"], .login-button').first.click()
            
            print("\n⏸️ SCRIPT PAUSED FOR MFA!")
            print("Please complete your Duo push or enter your code in the browser.")
            input("👉 PRESS 'ENTER' IN THIS TERMINAL ONCE YOU ARE FULLY LOGGED IN... ")
            
            print("Resuming script...")
            page.wait_for_load_state("networkidle", timeout=15000)
            context.storage_state(path=STATE_FILE)
            print("✅ Session saved successfully to state.json!\n")
            time.sleep(2)

        # --- LOOP TO DOWNLOAD FILES ---
        downloads_completed = 0
        current_date = datetime.now()

        while downloads_completed < num_files_to_get:
            # 1. Skip weekends
            if current_date.weekday() >= 5: 
                current_date -= timedelta(days=1)
                continue

            # 2. Format the date with NO DASHES: YYYYMMDD (e.g., 20260219)
            date_str = current_date.strftime("%Y%m%d")
            
            # 3. Apply the strict naming convention to ALL files
            filename = f"daily_volume_{date_str}.xlsx"
            save_path = os.path.join(SAVE_DIR, filename)

            # 4. Determine URL (Use static URL for the very first file, archive URLs for the rest)
            if downloads_completed == 0:
                url = STATIC_LATEST_URL
                print(f"--- Fetching LATEST File (Saving exactly as: {filename}) ---")
            else:
                url = f"https://www.cmegroup.com/ftp/daily_volume/daily_volume_{date_str}.xlsx"
                print(f"--- Fetching ARCHIVE File ({filename}) ---")

            if os.path.exists(save_path):
                print(f"✅ Already exists on disk. Skipping download.\n")
                downloads_completed += 1
                current_date -= timedelta(days=1)
                continue

            print(f"Attempting download from: {url}")
            
            try:
                with page.expect_download(timeout=10000) as download_info:
                    try:
                        response = page.goto(url)
                        
                        # Short-Circuit Logic for 404s/Holiday Pages
                        if response:
                            if response.status in [404, 403]:
                                raise ValueError("Holiday 404")
                            try:
                                page_text = page.content().lower()
                                if "sorry" in page_text and "exist" in page_text:
                                    raise ValueError("Holiday 404")
                            except:
                                pass

                    except Exception as e:
                        if "Download is starting" not in str(e) and "Holiday 404" not in str(e):
                            raise e 
                
                download = download_info.value
                download.save_as(save_path)
                
                print(f"✅ Successfully downloaded.\n")
                downloads_completed += 1
                time.sleep(1.5) 
                
            except (TimeoutError, ValueError) as e:
                if "Holiday 404" in str(e):
                    print(f"❌ 404/Holiday Page Detected! No report published for {date_str}. Skipping to previous day...\n")
                else:
                    print(f"❌ Timeout. Skipping to previous day...\n")
                
            except Exception as e:
                print(f"⚠️ An unexpected error occurred: {e}\n")
            
            current_date -= timedelta(days=1)
        print(f"🎉 All {num_files_to_get} target files are safely stored in {SAVE_DIR}!")
        time.sleep(2) 
        browser.close()

if __name__ == "__main__":
    # If the bash script passes a number, use it. Otherwise, default to 30.
    days_to_run = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    download_latest_cme_files(days_to_run)