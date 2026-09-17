# -*- coding: utf-8 -*-
"""data_epoch.py —— 数据 epoch manifest 工具(审计 §2.2 / §3.7 / Iteration 0).

审计关切:
  §2.2 运行时数据依赖不可复现(多个模块写死 /root/.hermes, 无缓存、epoch
       manifest 时不能复现历史结论)
  §3.7 "所有研究产物都必须保存原始数据 epoch, 以防缓存更新后同一日期内容
       发生变化"

本工具为研究链的**输入数据**(K 线缓存)生成不可变 epoch manifest:
  - 记录: 文件列表 + 每文件内容哈希(SHA256) + 文件数 + 总字节 + 生成时间
  - verify: 重算哈希并与 manifest 对比, 检测缓存是否被更新(内容漂移)
  - 集成: V697/V698 等研究链在生成产物时写入 manifest; 回放/比对前先 verify

纯只读工具; 不修改任何缓存或研究数据.
"""
import hashlib
import io
import json
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def file_sha256(path: str, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def build_manifest(cache_dir: str, pattern: str = "_daily_750.json",
                   max_files: int = 6000) -> dict:
    """扫描缓存目录, 生成 epoch manifest."""
    files = sorted(f for f in os.listdir(cache_dir) if pattern in f)
    files = files[:max_files]
    entries = {}
    total_bytes = 0
    for fn in files:
        fp = os.path.join(cache_dir, fn)
        try:
            total_bytes += os.path.getsize(fp)
            entries[fn] = file_sha256(fp)
        except OSError:
            entries[fn] = None
    return {
        "epoch_id": hashlib.sha256(
            json.dumps(entries, sort_keys=True).encode()).hexdigest()[:16],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cache_dir": cache_dir,
        "pattern": pattern,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": entries,
    }


def verify_manifest(manifest: dict, cache_dir: str | None = None) -> tuple[bool, dict]:
    """重算哈希并与 manifest 对比, 检测缓存漂移.

    Returns: (ok, detail)
      ok=True  -> 缓存与 manifest 一致(可复现)
      ok=False -> 检测到漂移(文件变更/新增/删除)
    """
    m_dir = manifest.get("cache_dir") or cache_dir
    pattern = manifest.get("pattern", "_daily_750.json")
    m_files = manifest.get("files", {})
    changed = []
    missing = []
    added = []
    for fn, h in m_files.items():
        fp = os.path.join(m_dir, fn) if m_dir else fn
        if not os.path.exists(fp):
            missing.append(fn)
            continue
        try:
            cur = file_sha256(fp)
        except OSError:
            cur = None
        if cur != h:
            changed.append(fn)
    if m_dir and os.path.isdir(m_dir):
        present = {f for f in os.listdir(m_dir) if pattern in f}
        added = sorted(present - set(m_files.keys()))
    ok = not (changed or missing or added)
    return ok, {"changed": changed[:20], "missing": missing[:20],
                "added": added[:20], "n_changed": len(changed),
                "n_missing": len(missing), "n_added": len(added)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 data_epoch.py <cache_dir> [verify <manifest.json>]")
        print("  build:   python3 data_epoch.py /root/.hermes/kline_cache")
        print("  verify:  python3 data_epoch.py <cache_dir> <manifest.json>")
        sys.exit(1)
    cache_dir = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == "verify" and len(sys.argv) >= 4:
        m = json.load(open(sys.argv[3], encoding="utf-8"))
        ok, detail = verify_manifest(m, cache_dir)
        print("验证: %s" % ("一致(可复现)" if ok else "漂移!"))
        print("  changed=%d missing=%d added=%d"
              % (detail["n_changed"], detail["n_missing"], detail["n_added"]))
        sys.exit(0 if ok else 2)
    else:
        m = build_manifest(cache_dir)
        out = os.path.join(os.path.dirname(os.path.abspath(cache_dir)),
                           "epoch_manifest_%s.json" % m["epoch_id"])
        json.dump(m, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        print("epoch manifest: %d 文件 / %d 字节 -> %s" % (m["file_count"],
                                                          m["total_bytes"], out))
        sys.exit(0)