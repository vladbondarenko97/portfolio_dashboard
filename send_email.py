import smtplib
import subprocess
import os
from config import required_env
import requests
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime, timedelta

# --- NTFY iPhone Notifications --- 
TOPIC = 'vladhq_alerts'
NTFY_URL = f"https://ntfy.sh/{TOPIC}"

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "mail.vlad.yt"
SMTP_PORT = 587 
SENDER_EMAIL = required_env("EMAIL_SENDER")
SENDER_PASSWORD = required_env("EMAIL_PASSWORD")
RECIPIENT_EMAIL = "contactvlad1k@gmail.com"

# --- ABSOLUTE PATHS ---
PYTHON_BIN = "/usr/local/Caskroom/miniconda/base/bin/python3"
MARKET_SCRIPT = "/Users/vladhq/Desktop/Python2026/market_reader.py"
OPTIONS_SCRIPT = "/Users/vladhq/Desktop/Python2026/options_scanner.py"
DATA_DIR = "/Users/vladhq/Desktop/CME_Data"

# ==========================================
# 1. MACRO CALENDAR ENGINE (7-DAY VIEW)
# ==========================================
def get_upcoming_macro():
    """Fetches High/Medium USD events for the next 7 days with weekend-gap protection."""
    # Added 'weekly' as a fallback to ensure rotation coverage
    urls = [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.xml"
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
            # We use a longer timeout to handle weekend server lag
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200: continue
            
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
    try:
        # Run market_reader.py (It reads tactical_ruling.txt internally)
        market_out = subprocess.check_output([PYTHON_BIN, MARKET_SCRIPT], text=True)
        
        # Run options_scanner.py
        options_out = subprocess.check_output([PYTHON_BIN, OPTIONS_SCRIPT], text=True)
        
        full_report = f"{macro_out_text}\n\n{market_out}\n\n{options_out}"
        
        print("\n" + "="*50)
        print("        FINAL ASSEMBLED REPORT OUTPUT")
        print("="*50 + "\n")
        print(full_report)
        print("\n" + "="*50 + "\n")
        
    except subprocess.CalledProcessError as e:
        print(f"Error running scripts: {e}")
        full_report = f"Script execution failed.\nError details: {e}\n\nPartial Macro Data:\n{macro_out_text}"

    # --- NTFY PUSH NOTIFICATIONS ---
    print("Sending NTFY iPhone notifications...")
    
    # 1. Macro Calendar Push
    requests.post(NTFY_URL, data=macro_out_text, headers={
        "Title": f"7-Day Macro Outlook {today_str}", 
        "Priority": "high", 
        "Tags": "calendar"
    })

    # 2. Market Brief Push
    requests.post(NTFY_URL, data=market_out, headers={
        "Title": f"Daily Market Report {today_str}", 
        "Priority": "urgent", 
        "Tags": "rotating_light"
    })

    # 3. Options Flow Push
    requests.post(NTFY_URL, data=options_out, headers={
        "Title": f"Options Brief {today_str}", 
        "Priority": "urgent", 
        "Tags": "triangular_flag_on_post"
    })

    # --- BUILD THE EMAIL ---
    msg = EmailMessage()
    msg['Subject'] = f"📈 Daily Market Report & Options Brief | {today_str}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg.set_content(full_report)

    # Image Chart Configuration
    chart_pairs = [
        ("ES Conviction", "chart1_es_conviction_7d.png", "chart1_es_conviction_30d.png"),
        ("Silver Conviction", "chart2_si_conviction_7d.png", "chart2_si_conviction_30d.png"),
        ("Silver Divergence", "chart3_silver_divergence_7d.png", "chart3_silver_divergence_30d.png"),
        ("SPY Options Flow", "chart4_spy_options_flow_7d.png", "chart4_spy_options_flow_30d.png"),
        ("Macro 10Y Yields", "chart5_macro_10y_yields_7d.png", "chart5_macro_10y_yields_30d.png"),
        ("COMEX Inventory", None, "chart6_comex_inventory_30d.png") 
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

    for title, file_7d, file_30d in chart_pairs:
        html_body += f"<h3>{title}</h3>\n<table><tr>"
        
        # 7-Day Chart
        if file_7d and os.path.exists(os.path.join(daily_dir, file_7d)):
            cid_7d = make_msgid()[1:-1] 
            html_body += f"<td><strong>7-Day Window</strong><br><img src='cid:{cid_7d}'></td>"
            images_to_attach.append((file_7d, cid_7d))
        else:
            html_body += "<td><em>7-Day chart not available</em></td>"
            
        # 30-Day Chart
        if file_30d and os.path.exists(os.path.join(daily_dir, file_30d)):
            cid_30d = make_msgid()[1:-1]
            html_body += f"<td><strong>30-Day Window</strong><br><img src='cid:{cid_30d}'></td>"
            images_to_attach.append((file_30d, cid_30d))
        else:
            html_body += "<td><em>30-Day chart not available</em></td>"
            
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
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Full report with 7-day calendar and charts routed to {RECIPIENT_EMAIL}!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    generate_and_send()