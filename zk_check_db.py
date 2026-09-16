import sqlite3
db = sqlite3.connect('D:\\chamcong\\zk_inject_workspace\\before_inject.db')
cur = db.cursor()
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print('Tables:', [r[0] for r in cur.fetchall()])
except Exception as e:
    print('Error:', e)
db.close()

import os
print('File size:', os.path.getsize('D:\\chamcong\\zk_inject_workspace\\before_inject.db'))
with open('D:\\chamcong\\zk_inject_workspace\\before_inject.db', 'rb') as f:
    print('First 100 bytes:', f.read(100))
    f.seek(-100, 2)
    print('Last 100 bytes:', f.read())
