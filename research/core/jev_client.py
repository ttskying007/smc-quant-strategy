# -*- coding: utf-8 -*-
"""core/jev_client.py — Jev(TypeSafe System One) 决策模型客户端(只读, 零依赖)

用户引入的外部判断模型: 将自然语言/结构化状态转为**类型化判断+概率**,
让我的代码(选股过滤/rank/alpha)拥有一个"语义判断"维度。
契约: POST https://api.typesafe.ai/v1/systemone  Bearer 鉴权
       {state, model: "jev-latest", questions: {id: {type, instructions, criteria}}}
安全纪律:
  - API key 只从环境变量 TYPESAFE_API_KEY 读, 永不写入文件/日志/commit
  - 本层只算判断, 不直接下单; "verify/escalate" 语义, 阈值由数据验证后定
性能(R65b 全量审计 10s/腿 教训):
  - 跨境长 RTT + urllib 无连接池 → 每腿新建 TLS 握手 = 大开销
  - 本模块新增 judge_many: http.client 连接复用(keep-alive) + ThreadPool 并发
"""
import json, os, urllib.request, urllib.error
from http.client import HTTPSConnection
from concurrent.futures import ThreadPoolExecutor

URL = "https://api.typesafe.ai/v1/systemone"
_HOST = "api.typesafe.ai"
_PATH = "/v1/systemone"


def _key():
    k = os.environ.get("TYPESAFE_API_KEY", "")
    if not k:
        raise RuntimeError("TYPESAFE_API_KEY 未设置")
    return k


def judge(state, questions, model="jev-latest", timeout=30):
    """state: dict/str; questions: {qid: {type,instructions,criteria?}}
    返回 {qid: answer}; 网络/鉴权错误抛出(调用方软失败)"""
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def judge_verbose(state, questions, model="jev-latest", timeout=30):
    """同 judge, 但 HTTP 错误时抛出带 body 的 RuntimeError"""
    try:
        return judge(state, questions, model, timeout)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = "<no body>"
        raise RuntimeError(f"HTTP {e.code}: {body}")


# ---- R67: 连接池 + 并发版(供全量回测/审计等批量场景) ----

class _Pooled:
    """单连接 keep-alive 复用: 避免每请求 TLS 握手(跨境大开销)。非线程安全 → 每线程各持一个。"""
    def __init__(self, timeout=30):
        self._conn = None
        self._timeout = timeout

    def call(self, body_bytes):
        if self._conn is None:
            self._conn = HTTPSConnection(_HOST, timeout=self._timeout)
        hdr = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}
        self._conn.request("POST", _PATH, body=body_bytes, headers=hdr)
        r = self._conn.getresponse()
        data = r.read()
        if r.status != 200:
            raise urllib.error.HTTPError(_PATH, r.status, "http error", r.headers, None)
        return json.loads(data.decode("utf-8"))

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


def judge_many(tasks, model="jev-latest", workers=6, timeout=40, retries=2):
    """批量并发送判断: tasks=[(state, questions), ...]; 每 worker 一个 keep-alive 连接。
    返回 list(与 tasks 同序): 成功=answers dict, 失败=None(不打断, 记返回值)。
    限流: 每 worker 请求间 sleep 0.05s(礼貌); retries 对瞬断/5xx 指数退避。
    """
    results = [None] * len(tasks)
    _slp = [0.05]

    def _one(i):
        state, qs = tasks[i]
        body = json.dumps({"state": state, "model": model, "questions": qs}).encode("utf-8")
        pool = _Pooled(timeout)
        try:
            for attempt in range(retries + 1):
                try:
                    ans = pool.call(body)
                    return i, ans.get("answers")
                except urllib.error.HTTPError as e:
                    if e.code == 429 and attempt < retries:
                        import time as _t
                        _t.sleep(1.5 * (attempt + 1))
                        pool.close()  # 可能被服务端关闭
                        continue
                    return i, None
                except Exception:
                    if attempt < retries:
                        import time as _t
                        _t.sleep(0.8 * (attempt + 1))
                        pool.close()
                        continue
                    return i, None
        finally:
            pool.close()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, ans in ex.map(_one, range(len(tasks))):
            results[i] = ans
    return results
