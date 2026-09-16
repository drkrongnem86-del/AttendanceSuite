import sqlite3
import os

fpath = r'D:\chamcong\test_backup.dat.extracted\data\ZKDB.db'
print(f'Reading: {fpath}')
print(f'Size: {os.path.getsize(fpath)} bytes')

conn = sqlite3.connect(fpath)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print(f'Tables: {tables}')

for table in tables:
    tname = table[0]
    cur.execute(f'SELECT count(*) FROM "{tname}"')
    cnt = cur.fetchone()[0]
    print(f'  {tname}: {cnt} rows')
    cur.execute(f'SELECT * FROM "{tname}" LIMIT 3')
    rows = cur.fetchall()
    for row in rows:
        print(f'    {row}')

conn.close()
