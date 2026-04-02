import sqlite3
import os

RACHEL_NUMBER = "+15738540964"
db_path = os.path.expanduser("~/Library/Messages/chat.db")

try:
    # Connect to the local iMessage database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get the sender of the most recent message in Rachel's thread
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

    # is_from_me == 1 means Vlad sent it from his iPhone/Mac
    if result and result[0] == 1:
        print("VLAD_REPLIED")
    else:
        print("NO_REPLY")
        
except Exception as e:
    print(f"ERROR: {e}")