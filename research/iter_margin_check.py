# -*- coding: utf-8 -*-
"""融资融券数据源验证：融资余额大幅增加（杠杆资金买入）信号
（之前弃用但未正式测过 —— 完成大资金数据源全覆盖）"""
import io, json, os, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# check margindb
db_paths = [r"E:\test\smc_project\margindb\margindb.db", r"E:\test\smc_project\hermes\margindb.db"]
for p in db_paths:
    if os.path.exists(p):
        print(f"融资融券 DB: {p}")
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  tables: {tables[:5]}")
        for t in tables[:2]:
            try:
                cur.execute(f"SELECT * FROM {t} LIMIT 1")
                cols = [d[0] for d in cur.description]
                row = cur.fetchone()
                print(f"  {t} 字段: {cols[:8]}")
                if row:
                    print(f"  {t} 样例: {str(row)[:200]}")
            except Exception as e:
                print(f"  {t}: {e}")
        conn.close()
        break
else:
    print("融资融券 DB 未找到（已弃用）")
    # check other paths
    import glob
    for f in glob.glob(r"E:\test\smc_project\**\*margin*", recursive=True)[:5]:
        print("  found:", f)
