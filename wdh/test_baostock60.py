# -*- coding: utf-8 -*-
"""Test baostock 60min full-history fetch for one stock (2023-01 to 2026-08)."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import baostock as bs

lg = bs.login()
print("login:", lg.error_code, lg.error_msg)
if lg.error_code != '0':
    sys.exit(1)

rs = bs.query_history_k_data_plus(
    "sh.600519", "date,time,open,high,low,close,volume,amount,adjustflag",
    start_date='2023-01-01', end_date='2026-08-18', frequency='60', adjustflag='2')
rows = []
while rs.error_code == '0' and rs.next():
    rows.append(rs.get_row_data())
print("fetch:", rs.error_code, rs.error_msg)
print("60m bars:", len(rows))
if rows:
    print("first:", rows[0][:7])
    print("last:", rows[-1][:7])
    # unique days
    days = set(r[0] for r in rows)
    print("unique days:", len(days), "range:", min(days), "-", max(days))
bs.logout()
