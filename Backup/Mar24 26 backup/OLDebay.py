import re
import json
import sys
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
import random
import time
from playwright.sync_api import sync_playwright
import csv

# --- 1. DYNAMIC SPOT PRICE INGESTION (TEXT PARSER) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'CME_Data')



def find_latest_files(lookback_days=5):
    today = datetime.now()
    found_dash = None
    found_tac = None

    for i in range(lookback_days + 1):
        check_date = today - timedelta(days=i)
        folder_str = check_date.strftime("%b-%d-%y")
        folder_path = os.path.join(DATA_DIR, folder_str)

        dash_path = os.path.join(folder_path, "volume_dashboard.txt")
        tac_path = os.path.join(folder_path, "tactical_ruling.txt")

        if not found_dash and os.path.exists(dash_path) and os.path.getsize(dash_path) > 0:
            found_dash = dash_path
        if not found_tac and os.path.exists(tac_path) and os.path.getsize(tac_path) > 0:
            found_tac = tac_path
        if found_dash and found_tac:
            break

    return found_dash, found_tac

def get_live_spot_price():
    _, tac_path = find_latest_files()
    if tac_path:
        try:
            tree = ET.parse(tac_path)
            root = tree.getroot()
            comex_element = root.find('.//shfe_silver/comex_spot')
            if comex_element is not None:
                price_str = comex_element.text.replace('$', '')
                return float(price_str)
        except Exception:
            pass
    return 67.80 

COMEX_SPOT = get_live_spot_price()

# --- 2. EBAY SCRAPING LOGIC ---
def parse_product_json(data, item_id):
    name = data.get("name", f"Silver Eagle (ID: {item_id})")
    offers = data.get("offers", {})
    
    if isinstance(offers, list) and len(offers) > 0:
        offers = offers[0]
        
    base_price = float(offers.get("price", 0.0))
    shipping_cost = 0.0
    shipping_details = offers.get("shippingDetails", [])
    if shipping_details and isinstance(shipping_details, list):
        rate = shipping_details[0].get("shippingRate", {})
        shipping_cost = float(rate.get("value", 0.0))
        
    status = offers.get("availability", "Unknown").split("/")[-1]
    
    return {
        "item_id": item_id,
        "name": name,
        "base_price": base_price,
        "shipping": shipping_cost,
        "total_cost": base_price + shipping_cost,
        "status": status
    }

def get_ebay_arbitrage_data(item_id, page):
    """Now accepts a Playwright 'page' object instead of using requests."""
    url = f"https://www.ebay.com/itm/{item_id}"
    
    try:
        # Navigate to the page, wait for the DOM to load
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        html_content = page.content()
        
        # Check for CAPTCHA blocks
        if "Security Measure" in html_content or "verify you are human" in html_content.lower() or "px-captcha" in html_content:
             return {"error": "Blocked by PerimeterX/CAPTCHA shield"}

        # 1. JSON-LD Extraction
        json_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)
        json_blocks += re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL | re.IGNORECASE)

        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                def find_product(obj):
                    if isinstance(obj, dict):
                        if obj.get("@type") == "Product": return obj
                        for value in obj.values():
                            res = find_product(value)
                            if res: return res
                    elif isinstance(obj, list):
                        for item in obj:
                            res = find_product(item)
                            if res: return res
                    return None

                product_data = find_product(data)
                if product_data:
                    return parse_product_json(product_data, item_id)
            except json.JSONDecodeError:
                continue 

        # 2. RAW HTML FALLBACK
        price_match = re.search(r'"price"\s*:\s*"([0-9\.]+)"', html_content)
        name_match = re.search(r'<title>(.*?)</title>', html_content)
        
        if price_match:
            base_price = float(price_match.group(1))
            raw_name = name_match.group(1) if name_match else "Silver Eagle"
            clean_name = re.sub(r' \| eBay$', '', raw_name)
            
            return {
                "item_id": item_id,
                "name": clean_name,
                "base_price": base_price,
                "shipping": 0.0, 
                "total_cost": base_price,
                "status": "Unknown (Fallback)"
            }

        return {"error": "Failed to extract data. Layout unrecognizable."}
    except Exception as e:
        return {"error": str(e)}

def log_arbitrage_ledger(cheapest_cost, avg_cost, comex_spot, item_count):
    """Appends the latest physical arbitrage metrics to a dedicated CSV ledger."""
    # Ensure the CME_Data directory exists
    data_dir = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
    os.makedirs(data_dir, exist_ok=True)
    
    file_path = os.path.join(data_dir, "physical_arbitrage_ledger.csv")
    file_exists = os.path.isfile(file_path)

    # The architectural order of your data columns
    headers = [
        "Datetime", "COMEX_Spot", "Cheapest_Eagle", "Average_Eagle", 
        "Cheapest_Premium_Dollars", "Cheapest_Premium_Percent", 
        "Average_Premium_Dollars", "Average_Premium_Percent", "Dealers_Scanned"
    ]

    # Calculate premiums for logging
    cheapest_prem_dlr = cheapest_cost - comex_spot if cheapest_cost else 0
    cheapest_prem_pct = (cheapest_prem_dlr / comex_spot * 100) if comex_spot else 0
    avg_prem_dlr = avg_cost - comex_spot if avg_cost else 0
    avg_prem_pct = (avg_prem_dlr / comex_spot * 100) if comex_spot else 0

    with open(file_path, mode='a', newline='') as f:
        writer = csv.writer(f)
        
        # Write headers if new file
        if not file_exists:
            writer.writerow(headers)
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Build the row
        row = [
            current_time, 
            round(comex_spot, 2), 
            round(cheapest_cost, 2) if cheapest_cost else "NaN", 
            round(avg_cost, 2) if avg_cost else "NaN",
            round(cheapest_prem_dlr, 2),
            round(cheapest_prem_pct, 2),
            round(avg_prem_dlr, 2),
            round(avg_prem_pct, 2),
            item_count
        ]
        
        writer.writerow(row)

# --- 3. EXECUTION ENGINE (PLAYWRIGHT) ---
if __name__ == "__main__":
    target_items = [
        "116932983600", # apmex 2026 1oz silver eagle
        "145163361842", # apmex random 1oz silver eagle
        "389246127742", # mcm 2026 1oz silver eagle
        "336328938777", # aydin 2026 1oz silver eagle
        "205844257920", # pinehurst 2026 1oz silver eagle
        "317033453863", # pinehurst random 1oz silver eagle
        "303115011716", # liberty coin random 1oz silver eagle
        "135152154013", # mcm random 1oz silver eagle
        "406597959293"  # dbs 2026 1 oz silver eagle
    ] 
    
    scraped_data = []

    # Boot up Playwright engine
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        for item in target_items:
            intel = get_ebay_arbitrage_data(item, page)
            
            if "error" not in intel:
                premium_dollars = intel['total_cost'] - COMEX_SPOT
                premium_percent = (premium_dollars / COMEX_SPOT) * 100
                
                intel['premium_dollars'] = premium_dollars
                intel['premium_percent'] = premium_percent
                scraped_data.append(intel)
                
            # --- JITTER ---
            time.sleep(random.uniform(1.5, 3.5))

        browser.close()

    # Sort by lowest premium
    scraped_data.sort(key=lambda x: x['premium_percent'])

    # --- FIRE LEDGER ENTRY ---
    if len(scraped_data) > 0:
        cheapest = scraped_data[0]['total_cost']
        avg = sum(d['total_cost'] for d in scraped_data) / len(scraped_data)
        log_arbitrage_ledger(cheapest, avg, COMEX_SPOT, len(scraped_data))

    # Build XML Root
    root = ET.Element("physical_arbitrage", 
                      comex_spot=f"${COMEX_SPOT:.2f}", 
                      timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      item_count=str(len(scraped_data)))

    for d in scraped_data:
        listing = ET.SubElement(root, "listing")
        listing.set("item_id", d['item_id'])
        
        clean_name = d['name'].replace(' | eBay', '')
        listing.set("name", clean_name[:60] + ("..." if len(clean_name) > 60 else "")) 
        
        listing.set("total_cost", f"${d['total_cost']:.2f}")
        listing.set("base_price", f"${d['base_price']:.2f}")
        listing.set("shipping", f"${d['shipping']:.2f}")
        listing.set("premium_dollars", f"${d['premium_dollars']:.2f}")
        listing.set("premium_percent", f"{d['premium_percent']:.2f}%")
        listing.set("status", d['status'])

    # Output Pretty XML
    raw_xml = ET.tostring(root, encoding='utf-8')
    pretty_xml = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    
    print(pretty_xml)