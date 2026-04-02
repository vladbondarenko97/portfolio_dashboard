import xml.etree.ElementTree as ET
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DATA_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "CME_Data")
TODAY_STR = datetime.now().strftime("%b-%d-%y") 

DASHBOARD_FILE = os.path.join(DATA_DIR, TODAY_STR, "volume_dashboard.txt")
TACTICAL_FILE = os.path.join(DATA_DIR, TODAY_STR, "tactical_ruling.txt")

def find_latest_files(lookback_days=5):
    """
    Looks back through the last X days to find the most recent 
    valid (non-empty) dashboard and tactical files.
    """
    today = datetime.now()
    found_dash = None
    found_tac = None

    for i in range(lookback_days + 1):
        check_date = today - timedelta(days=i)
        folder_str = check_date.strftime("%b-%d-%y")
        folder_path = os.path.join(DATA_DIR, folder_str)

        dash_path = os.path.join(folder_path, "volume_dashboard.txt")
        tac_path = os.path.join(folder_path, "tactical_ruling.txt")

        # Prioritize finding the most recent dashboard
        if not found_dash and os.path.exists(dash_path) and os.path.getsize(dash_path) > 0:
            found_dash = dash_path
            
        # Prioritize finding the most recent tactical ruling
        if not found_tac and os.path.exists(tac_path) and os.path.getsize(tac_path) > 0:
            found_tac = tac_path

        # If we found both (even if from different days), we can stop
        if found_dash and found_tac:
            break

    return found_dash, found_tac

def analyze_market():
    DASHBOARD_FILE, TACTICAL_FILE = find_latest_files(lookback_days=5)

    if not DASHBOARD_FILE or not TACTICAL_FILE:
        print(f"❌ Error: Could not find valid data files in the last 5 days of folders.")
        return

    # Parse BOTH XML files
    dash_tree = ET.parse(DASHBOARD_FILE)
    dash_root = dash_tree.getroot()
    
    tac_tree = ET.parse(TACTICAL_FILE)
    tac_root = tac_tree.getroot()

    # --- SAFE EXTRACTION HELPERS ---
    def safe_get(parent_node, path, default="unavailable"):
        """Gets text inside a tag: <tag>TEXT</tag>"""
        if parent_node is None: return default
        node = parent_node.find(path)
        return node.text if node is not None and node.text is not None else default

    def safe_get_attr(parent_node, path, attr_name, default="unavailable"):
        """Gets an attribute inside a tag: <tag attr="VALUE" />"""
        if parent_node is None: return default
        node = parent_node.find(path)
        return node.attrib.get(attr_name, default) if node is not None else default

    # --- 1. VMRI (From Tactical) ---
    vmri_score = safe_get(tac_root, './/VLAD_MACRO_RISK_INDEX/score')
    vmri_tier = safe_get(tac_root, './/VLAD_MACRO_RISK_INDEX/threat_level')

    # --- 2. UPCOMING MACRO EVENTS (From Tactical) ---
    catalyst_status = safe_get(tac_root, './/catalyst_calendar/status', 'CLEAR')
    events = []
    for ev in tac_root.findall('.//upcoming_macro_events/event'):
        e_date = ev.attrib.get('date', '')
        e_time = ev.attrib.get('time', '')
        e_impact = ev.attrib.get('impact', '')
        e_title = ev.attrib.get('title', '')
        e_est = ev.attrib.get('forecast', 'N/A')
        events.append(f"{e_date} @ {e_time} [{e_impact}] {e_title} (Est: {e_est})")
        
    tripwire_str = "\n  - ".join(events) if events else "None"

    # --- 3. COMEX INVENTORY (From Dashboard) ---
    vaults = dash_root.find('.//latest_vaults')
    if vaults is not None:
        registered = vaults.attrib.get('registered', '0')
        eligible = vaults.attrib.get('eligible', '0')
        daily_change = vaults.attrib.get('daily_change', '0')
    else:
        registered, eligible, daily_change = '0', '0', '0'

    # --- 4. PRECIOUS METALS & ARBS (Split Sources) ---
    spot = safe_get_attr(dash_root, './/market_prices/spot', 'price', 'unavailable')
    slv = safe_get_attr(dash_root, './/market_prices/slv', 'price', 'unavailable')
    sih26 = safe_get_attr(dash_root, './/market_prices/sih26', 'price', 'unavailable')
    gold = safe_get(tac_root, './/gold_price', 'unavailable')
    gsr = safe_get(tac_root, './/gold_silver_ratio', 'unavailable')

    # Detailed SHFE Arbitrage Extraction
    shfe_cny_kg = safe_get(tac_root, './/shfe_silver/cny_per_kg')
    shfe_usd_kg = safe_get(tac_root, './/shfe_silver/usd_per_kg')
    shfe_usd_oz = safe_get(tac_root, './/shfe_silver/usd_per_oz')
    shfe_comex  = safe_get(tac_root, './/shfe_silver/comex_spot')
    shfe_prem   = safe_get(tac_root, './/shfe_silver/premium')

    # FALLBACK: If spot is missing, calculate it via Gold / GSR
    if spot in ['unavailable', 'None', '0', '0.0'] and gold != 'unavailable' and gsr != 'unavailable':
        try:
            spot = str(round(float(gold) / float(gsr), 4))
        except:
            spot = 'unavailable'

    # --- 5. OPTIONS & SENTIMENT ---
    pc_nodes = dash_root.findall('.//sp500_put_call_flow/day')
    if pc_nodes:
        pc_ratio = float(pc_nodes[-1].attrib.get('ratio', '0'))
        if pc_ratio > 2.0: pc_status = "EXTREME FEAR (Heavy Put Buying)"
        elif pc_ratio > 1.3: pc_status = "BEARISH (Downside Hedging)"
        else: pc_status = "BULLISH / NEUTRAL"
    else:
        pc_ratio, pc_status = 0.0, "unavailable"

    vix = safe_get(tac_root, './/vix/value')
    vix_change = safe_get(tac_root, './/vix/change')

    # --- 6. SILVER DIVERGENCE ---
    div_nodes = dash_root.findall('.//silver_divergence/day')
    if div_nodes:
        inst_level = float(div_nodes[-1].attrib.get('institutions', '0'))
        retail_level = float(div_nodes[-1].attrib.get('retail', '0'))
        inst_status = "HIGH CONVICTION (Accumulating)" if inst_level >= 80 else "DISTRIBUTING"
        retail_status = "CAPITULATION" if retail_level < 50 else "BUYING"
    else:
        inst_level, retail_level, inst_status, retail_status = 0, 0, "unavailable", "unavailable"

    # --- 7. MACRO & LIQUIDITY ---
    ten_y_yield = safe_get(tac_root, './/macro_kill_switches/ten_year_treasury')
    dxy = safe_get(tac_root, './/dxy/value')
    oas = safe_get(tac_root, './/credit_markets/high_yield_oas_spread')
    rrp = safe_get(tac_root, './/liquidity_plumbing/reverse_repo_bn/latest')

    last_updated = safe_get(dash_root, './/last_updated', datetime.now().strftime("%Y-%m-%d %I:%M %p"))

    # --- 8. PHYSICAL ARBITRAGE (TOP 3 EAGLES) ---
    eagles_data = []
    phys_arb_node = tac_root.find('.//physical_arbitrage')
    
    if phys_arb_node is not None:
        for listing in phys_arb_node.findall('listing'):
            name = listing.attrib.get('name', 'Unknown')
            # Keep names concise for the terminal output
            if len(name) > 42: 
                name = name[:39] + "..."
                
            cost_str = listing.attrib.get('total_cost', '$0').replace('$', '').replace(',', '')
            prem_pct = listing.attrib.get('premium_percent', '0%')
            
            try:
                eagles_data.append({
                    'name': name,
                    'cost': float(cost_str),
                    'premium': prem_pct
                })
            except ValueError:
                continue
                
        # Sort ascending by cost to guarantee we get the cheapest ones
        eagles_data.sort(key=lambda x: x['cost'])
        
    # Format the top 3 items
    eagle_lines = []
    if eagles_data:
        for i, eagle in enumerate(eagles_data[:3]):
            eagle_lines.append(f"  {i+1}. ${eagle['cost']:.2f} | {eagle['premium']} Prem | {eagle['name']}")
        eagles_str = "\n".join(eagle_lines)
    else:
        eagles_str = "  - No listings available"

    last_updated = safe_get(dash_root, './/last_updated', datetime.now().strftime("%Y-%m-%d %I:%M %p"))

    # --- FORMATTING ---
    try:
        spot_f = f"${float(spot):.2f}" if spot not in ['unavailable', 'None'] else "unavailable"
        gold_f = f"${float(gold):.2f}" if gold not in ['unavailable', 'None'] else "unavailable"
    except:
        spot_f, gold_f = spot, gold

    report = f"""🌅 MORNING MARKET BRIEF 🌅
{last_updated}

🚨 VLAD MACRO RISK INDEX (VMRI)
  - Score: {vmri_score}
  - Threat Level: {vmri_tier}

⏰ CATALYST CALENDAR
  - Status: {catalyst_status}
  - Scheduled Events: 
  - {tripwire_str}

🏦 COMEX INVENTORY
  - Registered: {float(registered):,.2f}M oz
  - Eligible: {float(eligible):,.2f}M oz
  - Daily Change: {daily_change}

💰 PRECIOUS METALS & ARBS
  - Gold Price: {gold_f}
  - Gold/Silver Ratio: {gsr}
  - COMEX Spot Silver: {spot_f}

🇨🇳 SHANGHAI PHYSICAL ARBITRAGE (SGE)
  - SGE Quote: {shfe_cny_kg} CNY/kg
  - USD Equiv: {shfe_usd_kg}/kg ({shfe_usd_oz}/oz)
  - Arb vs COMEX: {shfe_comex}
  - Tax-Adj Premium: {shfe_prem}/oz

📉 S&P 500 OPTIONS FLOW
  - Put/Call Ratio: {pc_ratio:.2f} ({pc_status})
  - VIX (Volatility): {vix} ({vix_change})

🧠 SILVER DIVERGENCE
  - Institutions: {inst_level:.2f} [{inst_status}]
  - Retail: {retail_level:.2f} [{retail_status}]

🌍 MACRO & LIQUIDITY
  - 10Y Yield: {ten_y_yield}%
  - DXY (Dollar): {dxy}
  - High Yield OAS: {oas}
  - Fed Reverse Repo: ${rrp}B

  🦅 PHYSICAL ARBITRAGE (CHEAPEST EAGLES on eBay)
{eagles_str}
"""
    print(report)

if __name__ == "__main__":
    analyze_market()