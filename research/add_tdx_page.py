# -*- coding: utf-8 -*-
"""在 smc_unified.py 中插入 /tdx 路由 + build_tdx 页面（幂等）"""
import io, os, re
sys = __import__("sys")
io = __import__("io")
P = r"E:\test\smc_project\hermes\scripts\smc_unified.py"
src = open(P, encoding="utf-8").read()

# 1. 路由插入
route_old = "        elif path == '/funnel':\n            self._html(build_funnel())"
route_new = route_old + "\n        elif path == '/tdx':\n            self._html(build_tdx())"
if "elif path == '/tdx':" not in src:
    assert route_old in src, "funnel 路由未找到"
    src = src.replace(route_old, route_new, 1)
    print("已插入 /tdx 路由")
else:
    print("/tdx 路由已存在")

# 2. build_tdx 函数 —— 用列表拼接 HTML，避免嵌套三引号
lines = []
lines.append("def build_tdx():")
lines.append('    """数据源后端状态页（easy_tdx/pytdx/腾讯）—— 集成状态可视化。"""')
lines.append("    def _esc(x):")
lines.append('        return str(x if x is not None else "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")')
lines.append("    import sys as _sys")
lines.append('    _sys.path.insert(0, r"E:\\\\test\\\\smc_project\\\\research")')
lines.append("    try:")
lines.append("        from core import tdx_feed as TF")
lines.append("        st = TF.backend_status()")
lines.append("    except Exception as _e:")
lines.append('        return "<html><body><h2>tdx_feed 加载失败: %s</h2></body></html>" % _e')
lines.append("    _ten = st.get('tencent', {}); _pt = st.get('pytdx', {}); _easy = st.get('easy_tdx', {})")
lines.append("    def _badge(ok):")
lines.append('        return \'<span style="color:\' + (\'#3fb950">可用\' if ok else \'#f85149">不可用\') + \'</span>\'')
lines.append("    _r = []")
lines.append("    _r.append('<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\"><title>数据源后端状态</title>')")
lines.append("    _r.append('<meta http-equiv=\"refresh\" content=\"120\"><style>' + CSS + '</style></head><body>' + build_nav() + '</body>')")
lines.append("    _r.append('<div class=\"container\">')")
lines.append("    _r.append('<div class=\"card\"><h2>数据源后端状态（easy_tdx / pytdx / 腾讯）</h2>')")
lines.append("    _r.append('<p>激活后端: <b>' + _esc(st.get('active')) + '</b> — 统一适配器 <code>core/tdx_feed.py</code>，单一 bars 结构，后端不可用时自动回退腾讯缓存。</p></div>')")
lines.append("    _r.append('<div class=\"card\"><h3>腾讯缓存（现行主源）</h3><table>')")
lines.append("    _r.append('<tr><td>K线文件数</td><td>' + _esc(_ten.get('kline_files')) + ' 只</td></tr>')")
lines.append("    _r.append('<tr><td>状态</td><td>' + _badge(_ten.get('available')) + '</td></tr>')")
lines.append("    _r.append('<tr><td>目录</td><td><code>' + _esc(st.get('kline_dir')) + '</code></td></tr></table></div>')")
lines.append("    _r.append('<div class=\"card\"><h3>pytdx（通达信网络行情）</h3><table>')")
lines.append("    _r.append('<tr><td>状态</td><td>' + _badge(_pt.get('available')) + '</td></tr>')")
lines.append("    _r.append('<tr><td>说明</td><td>' + _esc(_pt.get('note')) + '</td></tr></table></div>')")
lines.append("    _r.append('<div class=\"card\"><h3>easy_tdx（通达信本地数据文件）</h3><table>')")
lines.append("    _r.append('<tr><td>状态</td><td>' + _badge(_easy.get('available')) + '</td></tr>')")
lines.append("    _r.append('<tr><td>说明</td><td>' + _esc(_easy.get('note')) + '</td></tr></table></div>')")
lines.append("    _r.append('<div class=\"card\"><h3>接入方式</h3><pre style=\"background:#161b22;padding:12px;border-radius:6px\">')")
lines.append("    _r.append('from core import tdx_feed as TF\\nbars = TF.get_daily(\"600519\")        # 统一日线（自动回退腾讯）\\nrt   = TF.get_realtime([\"600519\"])   # 实时报价（TDX 可用时）\\nff   = TF.get_fundflow(\"600519\")     # 资金/财务（TDX 可用时）\\nst   = TF.backend_status()           # 后端状态')")
lines.append("    _r.append('</pre></div></div></body></html>')")
lines.append("    return ''.join(_r)")

build_tdx_fn = "\n\n" + "\n".join(lines) + "\n\n"

anchor = "def build_compare():"
assert anchor in src, "build_compare 未找到"
src = src.replace(anchor, build_tdx_fn + anchor, 1)
print("已插入 build_tdx")

# 3. nav 链接
if "<a href='/tdx'>数据源</a>" not in src:
    src = src.replace("<a href='/funnel'>漏斗</a>", "<a href='/funnel'>漏斗</a><a href='/tdx'>数据源</a>")
    print("已加 nav /tdx 链接: " + str(src.count("<a href='/tdx'>数据源</a>")) + " 处")
else:
    print("nav /tdx 链接已存在")

open(P, "w", encoding="utf-8").write(src)
print("保存完成")