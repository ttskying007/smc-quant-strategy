# -*- coding: utf-8 -*-
"""core/manifest.py —— run_manifest 版本/数据血缘合同（审计蓝图迭代二 P0）

每次扫描/回测/纸面运行生成不可变 manifest.json：
code_commit / 参数哈希 / 数据快照 / 日历 / 执行模型 / artifact hash / 状态。
缺少核心字段 → status='invalid'，不得进入生产许可。
"""
import hashlib, json, os, subprocess, time


def _git_head(repo=None):
    try:
        repo = repo or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def param_hash(params):
    """参数档位哈希（稳定序列化）。"""
    if params is None:
        return "none"
    s = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def file_hash(path):
    """artifact 文件 SHA256。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return "missing"


REQUIRED_FIELDS = ["run_id", "strategy_id", "strategy_version", "code_commit",
                   "parameter_profile", "data_snapshot_id", "data_asof",
                   "cost_model_version", "execution_model_version", "created_at", "status",
                   "engine_sha256", "config_sha256"]


def _engine_files():
    """FIX(2026-09-06, 复审P0 版本脱钩): 执行内核+引擎哈希 —— 生产必须绑定。
    返回 dict {relpath: sha256}。"""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    targets = {
        "research/core/execution.py": os.path.join(base, "research", "core", "execution.py"),
        "research/config.py": os.path.join(base, "research", "config.py"),
        "wdh/wdh_engine.py": os.path.join(base, "wdh", "wdh_engine.py"),
        "research/paper_sim.py": os.path.join(base, "research", "paper_sim.py"),
    }
    out = {}
    for rel, p in targets.items():
        out[rel] = file_hash(p)
    return out


def build_manifest(run_id, strategy_id, strategy_version, params=None,
                   data_asof="", data_snapshot_id="", calendar_version="",
                   universe="", cost_model="cfg.fee0.2/slip0.001",
                   exec_model="core.execution:simulate",
                   artifact_paths=None, status="research",
                   repo=None, extra=None):
    """构造完整 manifest dict。缺核心字段时 status 降级为 'invalid'。"""
    m = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "code_commit": _git_head(repo),
        # FIX(2026-09-06, 复审P0): 版本脱钩 —— engine/config 哈希绑定，HEAD 只是文档提交时仍可锁定策略
        "engine_sha256": _engine_files()["research/core/execution.py"],
        "config_sha256": _engine_files()["research/config.py"],
        "parameter_profile": param_hash(params),
        "data_snapshot_id": data_snapshot_id,
        "data_asof": data_asof,
        "calendar_version": calendar_version,
        "universe_definition": universe,
        "cost_model_version": cost_model,
        "execution_model_version": exec_model,
        "artifact_hash": {p: file_hash(p) for p in (artifact_paths or [])},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": status,
    }
    if extra:
        m.update(extra)
    # 缺核心字段 → invalid
    for f in REQUIRED_FIELDS:
        if not m.get(f):
            m["status"] = "invalid"
            m["invalid_reason"] = f"missing field: {f}"
            break
    return m


def save_manifest(m, out_dir):
    """写 manifest.json（原子写，与账本一致）。"""
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "run_manifest.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return p


def validate_manifest(m):
    """门禁检查：核心字段齐全且 status 非 invalid。"""
    if m.get("status") == "invalid":
        return False, m.get("invalid_reason", "status=invalid")
    for f in REQUIRED_FIELDS:
        if not m.get(f):
            return False, f"missing: {f}"
    return True, "ok"


def validate_artifacts(m, require_nonempty=True):
    """FIX(2026-09-08, 复审 P0-1): artifact 存在性/空/哈希验证。
    审计要求: artifact 不存在、为空、hash 不匹配时状态必须为 INVALID，禁止发布候选。
    返回 (ok, reason_list)。m['artifact_hash'] = {path: hash_or_'missing'}。"""
    ah = m.get("artifact_hash") or {}
    bad = []
    for p, h in ah.items():
        if h == "missing":
            bad.append(f"{os.path.basename(p)}: 文件不存在")
            continue
        if require_nonempty:
            try:
                if os.path.getsize(p) == 0:
                    bad.append(f"{os.path.basename(p)}: 文件为空")
                    continue
            except OSError:
                bad.append(f"{os.path.basename(p)}: 无法访问")
                continue
        # 重算哈希核对（防半更新/旧数据）
        cur = file_hash(p)
        if cur != h:
            bad.append(f"{os.path.basename(p)}: 哈希不匹配({h} vs {cur})")
    if bad:
        m["status"] = "INVALID"
        m["invalid_reason"] = "; ".join(bad[:5])
        return False, bad
    return True, []


def finalize_manifest(m, artifact_paths, out_dir):
    """FIX(2026-09-08, 复审 P0-1): 生产合同收口 —— 验证 → 原子写 → artifact 复核。
    任何 artifact 缺失/空/哈希不符 → status=INVALID 且抛 RuntimeError(生产阻断)。
    返回 (manifest_path, valid_bool)。"""
    # 1. artifact 哈希记录
    m["artifact_hash"] = {p: file_hash(p) for p in (artifact_paths or [])}
    # 2. 原子写
    p = save_manifest(m, out_dir)
    # 3. artifact 复核（写后重新验证，捕获半更新/损坏）
    ok, bad = validate_artifacts(m)
    if not ok:
        m["status"] = "INVALID"
        m["invalid_reason"] = "; ".join(bad[:5])
        save_manifest(m, out_dir)  # 重写带 INVALID 状态
        raise RuntimeError(f"production run blocked: invalid manifest/artifact: {bad[:3]}")
    return p, True
