import smtplib
import subprocess
import os
import csv
from config import required_env
from core.api_client import api_client
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime, timedelta
import json

# --- NTFY iPhone Notifications --- 
TOPIC = 'vladhq_alerts'
NTFY_URL = f"https://ntfy.sh/{TOPIC}"

from config import DATA_DIR, EMAIL_SENDER, EMAIL_PASSWORD
from market_reader import analyze_market
from options_scanner import generate_options_report

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "mail.vlad.yt"
SMTP_PORT = 587 
RECIPIENT_EMAIL = "contactvlad1k@gmail.com"

# --- ABSOLUTE PATHS ---
PYTHON_BIN = "/usr/local/Caskroom/miniconda/base/bin/python3"
MARKET_SCRIPT = "/Users/vladhq/Desktop/Python2026/market_reader.py"
OPTIONS_SCRIPT = "/Users/vladhq/Desktop/Python2026/options_scanner.py"

# ==========================================
# 1. MACRO CALENDAR ENGINE (7-DAY VIEW)
# ==========================================
def get_upcoming_macro():
    """Fetches High/Medium USD events for the next 7 days with weekend-gap protection."""
    # Added 'weekly' as a fallback to ensure rotation coverage
    urls = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    today = datetime.now()
    # We generate dates in two formats to catch any XML variation
    target_dates = [(today + timedelta(days=i)).strftime('%m-%d-%Y') for i in range(8)]
    target_dates_alt = [(today + timedelta(days=i)).strftime('%-m-%-d-%Y') for i in range(8)]
    all_targets = set(target_dates + target_dates_alt)
    
    text_output = ["📅 7-DAY MACRO OUTLOOK (USD)"]
    text_output.append("="*40)
    
    events_found = False
    seen_events = set()

    for url in urls:
        try:
            # We use a short timeout to prevent hangs when rate-limited
            resp = api_client.get(url, headers=headers, timeout=3)
            
            # Check if we got a successful XML response (ForexFactory returns HTML on 429)
            if resp.status_code != 200:
                print(f"DEBUG: Macro feed returned status {resp.status_code} for {url}")
                continue

            if 'text/xml' not in resp.headers.get('Content-Type', ''):
                print(f"DEBUG: Macro feed returned non-XML content for {url}")
                continue

            root = ET.fromstring(resp.content)
            for event in root.findall('event'):
                # 1. Filter: Country & Impact
                country = event.findtext('country', '')
                impact = event.findtext('impact', '')
                
                if country != 'USD': continue
                if impact not in ['High', 'Medium']: continue
                
                # 2. Date Matching (Robust)
                date = event.findtext('date', '')
                if date in all_targets:
                    title = event.findtext('title', '')
                    time = event.findtext('time', '')
                    
                    # Prevent dupes across feed overlaps
                    event_key = f"{date}-{time}-{title}"
                    if event_key in seen_events: continue
                    seen_events.add(event_key)

                    forecast = event.findtext('forecast', 'N/A')
                    previous = event.findtext('previous', 'N/A')
                    icon = "🚨" if impact == 'High' else "⚠️"
                    
                    text_output.append(f"{date} @ {time}")
                    text_output.append(f"{icon} [{impact}] {title}")
                    text_output.append(f"   Est: {forecast} | Prev: {previous}")
                    text_output.append("-" * 40)
                    events_found = True
                    
        except Exception as e:
            # If a specific URL fails, we want to know, but keep going
            print(f"DEBUG: Feed failure on {url}: {e}")
            continue 
            
    if not events_found:
        text_output.append("No High/Medium impact USD events scheduled for the next 7 days.")
        text_output.append("(Check if it is a US Bank Holiday weekend)")
        
    return "\n".join(text_output)

# ==========================================
# 1b. SLV INSTITUTIONAL FLOW ENGINE
# ==========================================
def get_slv_institutional_data():
    """Reads the latest SLV dark pool + GEX data from the institutional scanner ledger."""
    ledger_path = os.path.join(DATA_DIR, "equities_darkpool_gex_ledger.csv")
    
    if not os.path.exists(ledger_path):
        return "\n🦅 SLV INSTITUTIONAL FLOW: Ledger not found. Run institutional_scanner.py first.\n"
    
    try:
        with open(ledger_path, 'r') as f:
            reader = csv.DictReader(f)
            all_rows = [r for r in reader if r.get('Ticker', '').upper() == 'SLV']
        
        if not all_rows:
            return "\n🦅 SLV INSTITUTIONAL FLOW: No SLV data in ledger yet.\n"
        
        # Get latest entry
        latest = all_rows[-1]
        
        text = ["\n🦅 SLV INSTITUTIONAL DARK POOL FLOW"]
        text.append("=" * 45)
        text.append(f"  Scan Date:       {latest.get('Date', 'N/A')}")
        text.append(f"  Spot Price:      ${latest.get('Spot_Price', 'N/A')}")
        text.append(f"  DP Sentiment:    {latest.get('DP_Sentiment', 'N/A')}")
        text.append(f"  DP VWAP:         ${latest.get('DP_VWAP', 'N/A')}")
        text.append(f"  Block Volume:    {latest.get('DP_Total_Vol', 'N/A')}")
        text.append(f"  Notional (USD):  ${latest.get('DP_Notional_USD', 'N/A')}")
        text.append(f"  Largest Block:   {latest.get('DP_Largest_Block', 'N/A')}")
        text.append(f"  Bull Volume:     {latest.get('DP_Bull_Vol', 'N/A')}")
        text.append(f"  Bear Volume:     {latest.get('DP_Bear_Vol', 'N/A')}")
        text.append("-" * 45)
        text.append(f"  GEX Call Wall:   ${latest.get('GEX_Call_Wall', 'N/A')}")
        text.append(f"  GEX Put Wall:    ${latest.get('GEX_Put_Wall', 'N/A')}")
        text.append(f"  GEX Zero Gamma:  ${latest.get('GEX_Zero_Gamma', 'N/A')}")
        
        # Historical trend (last 5 unique entries)
        if len(all_rows) >= 2:
            text.append("\n  📊 RECENT SENTIMENT TREND:")
            
            # Keep only the latest entry per day
            unique_daily = {}
            for r in all_rows:
                date_str = r.get('Date', '?')[:10]
                unique_daily[date_str] = r
                
            recent_vals = list(unique_daily.values())
            recent = recent_vals[-5:] if len(recent_vals) >= 5 else recent_vals
            
            for row in recent:
                date = row.get('Date', '?')[:10]
                sent = row.get('DP_Sentiment', '?')
                vwap = row.get('DP_VWAP', '?')
                text.append(f"    {date} → {sent} (VWAP: ${vwap})")
        
        text.append("=" * 45)
        return "\n".join(text)
    
    except Exception as e:
        return f"\n🦅 SLV INSTITUTIONAL FLOW: Error reading ledger: {e}\n"

def get_institutional_json():
    """Returns latest institutional data for SLV and SPY in raw JSON format."""
    ledger_path = os.path.join(DATA_DIR, "equities_darkpool_gex_ledger.csv")
    if not os.path.exists(ledger_path):
        return "{}"
    
    try:
        with open(ledger_path, 'r') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        # Get latest entry for SLV and SPY
        slv_latest = next((r for r in reversed(data) if r.get('Ticker', '').upper() == 'SLV'), {})
        spy_latest = next((r for r in reversed(data) if r.get('Ticker', '').upper() == 'SPY'), {})
        
        dump = {
            "slv_institutional_latest": slv_latest,
            "spy_institutional_latest": spy_latest,
            "system_timestamp": datetime.now().isoformat()
        }
        return json.dumps(dump, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

# ==========================================
# 2. MASTER GENERATOR
# ==========================================
def generate_and_send():
    # Initialize variables to prevent UnboundLocalError
    market_out = "Market report failed to generate."
    options_out = "Options scan failed to generate."
    full_report = ""
    
    today_str = datetime.now().strftime('%b-%d-%y')
    daily_dir = os.path.join(DATA_DIR, today_str)

    print("Gathering 7-day macro calendar...")
    macro_out_text = get_upcoming_macro()

    print("Synthesizing market and options data...")
    
    print("Reading SLV institutional dark pool data...")
    slv_institutional_text = get_slv_institutional_data()
    
    try:
        # Run market_reader.py (It reads tactical_ruling.txt internally)
        market_out = analyze_market()
        
        # Run options_scanner.py
        options_out = generate_options_report()
        
        full_report = f"{macro_out_text}\n\n{slv_institutional_text}\n\n{market_out}\n\n{options_out}"
        
        # Append RAW JSON Data for LLM/Trade Context
        raw_json = get_institutional_json()
        full_report += f"\n\n========================================\n ⚡ RAW INSTITUTIONAL JSON SNAPSHOT\n========================================\n{raw_json}"
        
        print("\n" + "="*50)
        print("        FINAL ASSEMBLED REPORT OUTPUT")
        print("="*50 + "\n")
        print(full_report)
        print("\n" + "="*50 + "\n")
        
    except Exception as e:
        print(f"Error running scripts: {e}")
        full_report = f"Script execution failed.\nError details: {e}\n\nPartial Macro Data:\n{macro_out_text}"

    # --- NTFY PUSH NOTIFICATIONS ---
    print("Sending NTFY iPhone notifications...")
    
    # 1. Macro Calendar Push
    try:
        api_client.post(NTFY_URL, data=macro_out_text.encode('utf-8'), headers={
            "Title": f"7-Day Macro Outlook {today_str}", 
            "Priority": "high", 
            "Tags": "calendar"
        })
    except Exception as e:
        print(f"Failed to send NTFY notification: {e}")

    # 2. Market Brief Push
    try:
        api_client.post(NTFY_URL, data=market_out.encode('utf-8'), headers={
            "Title": f"Daily Market Report {today_str}", 
            "Priority": "urgent", 
            "Tags": "rotating_light"
        })
    except Exception as e:
        pass

    # 3. Options Flow Push
    try:
        api_client.post(NTFY_URL, data=options_out.encode('utf-8'), headers={
            "Title": f"Options Brief {today_str}", 
            "Priority": "urgent", 
            "Tags": "triangular_flag_on_post"
        })
    except Exception as e:
        pass

    # 4. SLV Dark Pool Push
    try:
        api_client.post(NTFY_URL, data=slv_institutional_text.encode('utf-8'), headers={
            "Title": f"SLV Institutional Flow {today_str}", 
            "Priority": "high", 
            "Tags": "eagle"
        })
    except Exception as e:
        pass

    # --- BUILD THE EMAIL ---
    msg = EmailMessage()
    msg['Subject'] = f"📈 Daily Market Report & Options Brief | {today_str}"
    msg['From'] = EMAIL_SENDER
    msg['To'] = RECIPIENT_EMAIL
    msg.set_content(full_report)

    # Image Chart Configuration
    chart_pairs = [
        ("ES Conviction", "chart1_es_conviction_7d.png", "chart1_es_conviction_30d.png"),
        ("Silver Conviction", "chart2_si_conviction_7d.png", "chart2_si_conviction_30d.png"),
        ("Silver Divergence", "chart3_silver_divergence_7d.png", "chart3_silver_divergence_30d.png"),
        ("SPY Options Flow", "chart4_spy_options_flow_7d.png", "chart4_spy_options_flow_30d.png"),
        ("Macro 10Y Yields", "chart5_macro_10y_yields_7d.png", "chart5_macro_10y_yields_30d.png"),
        ("COMEX Inventory", None, "chart6_comex_inventory_30d.png"),
        ("Bitcoin Ratios", "chart7_crypto_ratios_30d.png", "chart7_crypto_ratios_1y.png"),
        ("Metals Prices", "chart8_metals_price_30d.png", "chart8_metals_price_1y.png")
    ]

    # HTML Body Construction
    html_body = f"""
    <html>
      <head>
        <style>
          body {{ font-family: monospace; color: #333; }}
          pre {{ font-family: monospace; white-space: pre-wrap; }}
          table {{ width: 100%; max-width: 1400px; margin-bottom: 30px; border-collapse: collapse; }}
          td {{ width: 50%; padding: 10px; vertical-align: top; text-align: center; }}
          img {{ max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px; }}
          h3 {{ font-family: sans-serif; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        </style>
      </head>
      <body>
        <pre>{full_report}</pre>
        <hr>
        <h2>Market Charts</h2>
    """

    images_to_attach = []

    for title, file_1, file_2 in chart_pairs:
        html_body += f"<h3>{title}</h3>\n<table><tr>"
        
        def get_label(filename):
            if not filename: return "Chart"
            if '7d' in filename: return "7-Day Window"
            if '30d' in filename: return "30-Day Window"
            if '1y' in filename: return "1-Year Window"
            return "Chart"

        # First Chart
        if file_1 and os.path.exists(os.path.join(daily_dir, file_1)):
            cid_1 = make_msgid()[1:-1] 
            html_body += f"<td><strong>{get_label(file_1)}</strong><br><img src='cid:{cid_1}'></td>"
            images_to_attach.append((file_1, cid_1))
        else:
            html_body += f"<td><em>{get_label(file_1)} not available</em></td>"
            
        # Second Chart
        if file_2 and os.path.exists(os.path.join(daily_dir, file_2)):
            cid_2 = make_msgid()[1:-1]
            html_body += f"<td><strong>{get_label(file_2)}</strong><br><img src='cid:{cid_2}'></td>"
            images_to_attach.append((file_2, cid_2))
        else:
            html_body += f"<td><em>{get_label(file_2)} not available</em></td>"
            
        html_body += "</tr></table>\n"

    html_body += "</body></html>"
    msg.add_alternative(html_body, subtype='html')

    # Attach images to HTML
    html_part = msg.get_payload()[1] 
    for filename, cid in images_to_attach:
        filepath = os.path.join(daily_dir, filename)
        with open(filepath, 'rb') as img_file:
            img_data = img_file.read()
            html_part.add_related(img_data, maintype='image', subtype='png', cid=f"<{cid}>")

    # Final Send Logic
    print(f"Connecting to {SMTP_SERVER}...")
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Full report with 7-day calendar and charts routed to {RECIPIENT_EMAIL}!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    generate_and_send()