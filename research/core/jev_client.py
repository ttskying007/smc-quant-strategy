# -*- coding: utf-8 -*-
"""core/jev_client.py — Jev(TypeSafe System One) 决策模型客户端(只读, 零依赖)

用户引入的外部判断模型: 将自然语言/结构化状态转为**类型化判断+概率**,
让我的代码(选股过滤/rank/alpha)拥有一个"语义判断"维度。
契约: POST https://api.typesafe.ai/v1/systemone  Bearer 鉴权
       {state, model: "jev-latest", questions: {id: {type, instructions, criteria}}}
安全纪律:
  - API key 只从环境变量 TYPESAFE_API_KEY 读, 永不写入文件/日志/commit
  - 本层只算判断, 不直接下单; "verify/escalate" 语义, 阈值由数据验证后定
"""
import json, os, urllib.request

URL = "https://api.typesafe.ai/v1/systemone"


def judge(state, questions, model="jev-latest", timeout=30):
    """state: dict/str; questions: {qid: {type,instructions,criteria?}}
    返回 {qid: answer}; 网络/鉴权错误抛出(调用方软失败)"""
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY 未设置")
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def judge_verbose(state, questions, model="jev-latest", timeout=30):
    """同 judge, 但 HTTP 错误时抛出带 body 的 RuntimeError"""
    import urllib.error
    try:
        return judge(state, questions, model, timeout)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = "<no body>"
        raise RuntimeError(f"HTTP {e.code}: {body}")
