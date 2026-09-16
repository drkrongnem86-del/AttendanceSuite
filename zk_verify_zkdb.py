"""Verify web-extracted ZKDB.db is a valid SQLite database"""
import sqlite3
import os

db_path = r'D:/chamcong/zk_fw_attempts/business_extracted/000_ZKDB.db'
print(f'File size: {os.path.getsize(db_path)} bytes')
print(f'Header: {open(db_path, "rb").read(16).hex()}')

# Test as SQLite
try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print(f'Tables: {[t[0] for t in tables]}')
    for t in tables:
        name = t[0]
        cur.execute(f'SELECT COUNT(*) FROM "{name}"')
        cnt = cur.fetchone()[0]
        print(f'  {name}: {cnt} rows')
    conn.close()
    print('SUCCESS - ZKDB.db is valid SQLite')
except Exception as e:
    print(f'SQLite error: {e}')