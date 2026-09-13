#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect('D:/chamcong/zk_data_extracted/ZKDB.db')
conn.text_factory = lambda b: b.decode('cp1252', errors='replace') if isinstance(b, bytes) else b
c = conn.cursor()
c.execute("SELECT User_PIN FROM USER_INFO WHERE User_PIN LIKE '%47%' LIMIT 10")
print('User 47 variants:', c.fetchall())
c.execute("""
    SELECT User_PIN, COUNT(DISTINCT substr(Verify_Time, 1, 10)) as days,
           COUNT(*) as punches
    FROM ATT_LOG
    WHERE substr(Verify_Time, 1, 7) = '2026-09'
    GROUP BY User_PIN
    ORDER BY punches DESC
    LIMIT 5
""")
print('Top 5:', c.fetchall())
c.execute("SELECT COUNT(*) FROM ATT_LOG WHERE User_PIN='47'")
print('47 punches:', c.fetchall())
c.execute("SELECT DISTINCT User_PIN FROM ATT_LOG WHERE substr(Verify_Time, 1, 7)='2026-09' ORDER BY punches DESC LIMIT 5" if False else "SELECT DISTINCT User_PIN FROM ATT_LOG WHERE substr(Verify_Time, 1, 7)='2026-09' LIMIT 5")
print('Distinct users in Sep:', c.fetchall())
