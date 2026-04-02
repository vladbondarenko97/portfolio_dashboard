import sys
import time
import sqlite3
import os

if len(sys.argv) < 2:
    sys.exit(1)

RACHEL_NUMBER = "+15738540964"
ai_reply = sys.argv[1]

# 1. Silently wait 30 minutes in the background
time.sleep(1800)

# 2. Wake up and check the database
try:
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = f"""
    SELECT m.is_from_me
    FROM message m
    JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
    JOIN chat c ON cmj.chat_id = c.ROWID
    WHERE c.chat_identifier LIKE '%{RACHEL_NUMBER.replace('+', '')}%'
    ORDER BY m.date DESC LIMIT 1;
    """
    cursor.execute(query)
    result = cursor.fetchone()
    conn.close()

    # 3. Deliver if Vlad hasn't intervened
    if not (result and result[0] == 1):
        # Escape quotes so the AppleScript doesn't break
        escaped_reply = ai_reply.replace('"', '\\"').replace("'", "\\'")
        
        # Blast the AI's pre-computed reply using the native Messages app
        applescript = f'tell application "Messages" to send "{escaped_reply}" to buddy "{RACHEL_NUMBER}"'
        os.system(f"osascript -e '{applescript}'")

except Exception as e:
    pass # Fail silently so it doesn't leave stray error logs