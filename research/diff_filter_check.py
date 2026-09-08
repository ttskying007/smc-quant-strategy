# -*- coding: utf-8 -*-
"""对拍新旧事件过滤 + 退出语义差异归因（第七轮全量回测复检）"""
import io, sys, sqlite3
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.events import classify_title


def is_strong_old(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
old_only = new_only = both = 0
ex = []
for (t,) in cur.fetchall():
    o = is_strong_old(t)
    n_ev, n_kind, n_pol = classify_title(t)[:3]
    n = bool(n_ev and n_pol > 0)
    if o and not n:
        old_only += 1
        if len(ex) < 10:
            ex.append(("旧过新拒", t[:48]))
    elif n and not o:
        new_only += 1
        if len(ex) < 20:
            ex.append(("新过旧拒", t[:48]))
    elif o and n:
        both += 1
print(f"旧filter独有: {old_only} | 新filter独有: {new_only} | 两者都过: {both}")
for tag, t in ex:
    print(f"  [{tag}] {t}")
conn.close()