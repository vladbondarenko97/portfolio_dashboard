import sys
import requests

# We expect the AI to run: python3 notify.py "Message body" "Optional Title"
if len(sys.argv) < 2:
    print("Error: Missing message body.")
    sys.exit(1)

# Grab the arguments passed by the AI
body_text = sys.argv[1]
# Default title if the AI doesn't provide one
title_text = sys.argv[2] if len(sys.argv) > 2 else "AI Assistant"

url = "https://ntfy.sh/vladhq_alerts"
headers = {
    "Title": title_text,
    "Priority": "urgent",
    "Tags": "robot,rotating_light"
}

try:
    # Safely encode the AI's text to handle any weird characters
    res = requests.post(url, data=body_text.encode('utf-8'), headers=headers)
    res.raise_for_status()
    print("✅ Alert sent to Vlad successfully.")
except Exception as e:
    print(f"❌ Failed to send alert: {e}")