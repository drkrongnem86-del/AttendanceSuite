"""Check Options table from web-extracted ZKDB.db"""
import sqlite3

db_path = r'D:/chamcong/zk_fw_attempts/business_extracted/000_ZKDB.db'

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check schema
cur.execute("SELECT sql FROM sqlite_master WHERE name='Options'")
print('Options schema:')
print(cur.fetchone()[0])

print('\nOptions content:')
cur.execute("SELECT * FROM Options LIMIT 20")
cols = [d[0] for d in cur.description]
print('Columns:', cols)
for row in cur.fetchall():
    print(f'  {dict(zip(cols, row))}')

# Sample ATT_LOG
print('\nATT_LOG schema:')
cur.execute("SELECT sql FROM sqlite_master WHERE name='ATT_LOG'")
print(cur.fetchone()[0])

print('\nATT_LOG first 5 rows:')
cur.execute("SELECT BADGENUMBER, CHECKTIME, CHECKTYPE, VERIFYCODE FROM ATT_LOG LIMIT 5")
for row in cur.fetchall():
    print(f'  {row}')

conn.close()