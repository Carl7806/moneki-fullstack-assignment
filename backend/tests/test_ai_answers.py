"""AI 回答自动化测试：断言 AI 回答中的数字与数据库查询结果一致。

分两层：
1. 确定性测试（不联网）：用假 LLM 客户端，走完整「选工具 → 真实 SQL → 数字回填 → 生成回答」链路；
2. 集成测试（需 DEEPSEEK_API_KEY）：真实调用 DeepSeek，抽取回答中的数字与 db 逐项比对。
"""
import json
import os
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import db
from ai import chat as chat_module
from ai.chat import chat, chat_stream
from ai.tools import run_tool
from analytics import detect_sales_anomalies


# ---------- 假 LLM 客户端（确定性测试用，不联网） ----------

class FakeToolCall:
    def __init__(self, call_id, name, args):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=json.dumps(args))


class FakeMessage:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls or []
        self.content = content


class _Resp:
    def __init__(self, message):
        self.choices = [SimpleNamespace(message=message)]


class FakeDelta:
    def __init__(self, content):
        self.content = content


class FakeChunk:
    def __init__(self, content):
        self.choices = [SimpleNamespace(delta=FakeDelta(content))]


def _tool_resp(name, args):
    return _Resp(FakeMessage(tool_calls=[FakeToolCall("call_1", name, args)]))


def _final_resp(content):
    return _Resp(FakeMessage(content=content))


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)(kwargs)


class FakeClient:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


def _extract_numbers(text):
    """抽取文本中全部数字（容忍千分位逗号、小数）。"""
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def _tool_content(messages):
    """取最后一次注入给模型的工具结果 JSON（messages 里可能混有消息对象，只取 dict）。"""
    tool_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert tool_msgs, "未把工具结果回填给模型"
    return json.loads(tool_msgs[-1]["content"])


# ---------- 确定性测试：工具 = 真实 SQL ----------

def test_summary_tool_matches_db():
    summary = run_tool("get_revenue_summary", {})
    expected = db.get_summary()
    assert summary == expected
    assert summary["revenue"] > 0
    assert summary["orders"] > 0


def test_store_ranking_tool_matches_db_desc():
    ranking = run_tool("get_store_ranking", {})
    assert ranking == db.get_store_ranking()
    assert ranking
    revenues = [r["revenue"] for r in ranking]
    assert revenues == sorted(revenues, reverse=True)


def test_product_sales_tool_matches_db():
    got = run_tool("get_product_sales", {"product_name": "poke"})
    expected = db.get_product_sales("poke")
    assert got == expected
    assert got, "poke 应能命中商品"


def test_anomaly_detection_math():
    base = [{"store_name": "A", "date": f"2026-05-{i:02d}", "revenue": 100.0} for i in range(1, 21)]
    spike = {"store_name": "A", "date": "2026-05-21", "revenue": 1000.0}
    anomalies = detect_sales_anomalies(base + [spike], threshold=2.0)
    assert anomalies
    assert anomalies[0]["date"] == "2026-05-21"
    assert anomalies[0]["deviation"] == "偏高"
    assert anomalies[0]["z_score"] > 2.0


def test_anomaly_detection_ignores_flat_series():
    rows = [
        {"store_name": "A", "date": "2026-05-01", "revenue": 100.0},
        {"store_name": "A", "date": "2026-05-02", "revenue": 100.0},
        {"store_name": "A", "date": "2026-05-03", "revenue": 100.0},
        {"store_name": "A", "date": "2026-05-04", "revenue": 100.0},
    ]
    assert detect_sales_anomalies(rows) == []


# ---------- 确定性测试：编排链路回答数字 == 数据库 ----------

def test_chat_answers_with_real_db_number():
    def first(kwargs):
        return _tool_resp("get_revenue_summary", {})

    def second(kwargs):
        result = _tool_content(kwargs["messages"])
        return _final_resp(f"全期总营业额为 {result['revenue']:,.2f} 元")

    fake = FakeClient([first, second])
    with patch.object(chat_module, "_get_client", return_value=fake):
        out = chat("全程总营业额是多少？")

    expected = db.get_summary()
    nums = _extract_numbers(out["answer"])
    assert len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["tool"] == "get_revenue_summary"
    assert nums, "回答应包含数字"
    assert abs(nums[0] - expected["revenue"]) < 0.01


def test_chat_stream_flows_db_numbers():
    def first(kwargs):
        return _tool_resp("get_revenue_summary", {})

    def loop_again(kwargs):
        # 工具结束后模型还会再被问一次是否继续调用工具，此处返回「不继续」
        return _Resp(FakeMessage())

    def stream_final(kwargs):
        assert kwargs.get("stream") is True
        result = _tool_content(kwargs["messages"])
        return [FakeChunk(str(round(result["revenue"], 2)))]

    fake = FakeClient([first, loop_again, stream_final])
    with patch.object(chat_module, "_get_client", return_value=fake):
        events = list(chat_stream("总营业额？"))

    parsed = [json.loads(e[len("data: "):].strip()) for e in events]
    types = [p["type"] for p in parsed]
    assert "status" in types and "delta" in types and "done" in types

    deltas = "".join(p.get("content", "") for p in parsed if p["type"] == "delta")
    assert abs(_extract_numbers(deltas)[0] - db.get_summary()["revenue"]) < 0.01

    done = next(p for p in parsed if p["type"] == "done")
    assert done["tool_calls"] and done["tool_calls"][0]["tool"] == "get_revenue_summary"


# ---------- 确定性测试：异常预警关键词兜底 ----------

def test_anomaly_keyword_detection():
    from ai.tools import wants_anomaly_check
    assert wants_anomaly_check("最近有没有营业额异常？")
    assert wants_anomaly_check("帮我做营业额预警")
    assert wants_anomaly_check("哪家店突然暴跌")
    assert not wants_anomaly_check("6月总营业额是多少")


def test_anomaly_intent_triggers_deterministic_tool():
    def final(kwargs):
        result = _tool_content(kwargs["messages"])
        assert isinstance(result, dict)
        assert result["total"] == len(result["items"])
        return _final_resp(f"检测到 {result['total']} 条营业额异常记录")

    fake = FakeClient([final])
    with patch.object(chat_module, "_get_client", return_value=fake):
        out = chat("最近哪些门店的营业额有异常？")

    tools = [tc["tool"] for tc in out["tool_calls"]]
    assert "get_sales_anomalies" in tools
    # 注入的结果必须与真实 SQL 检测结果逐字一致
    expected = run_tool("get_sales_anomalies", {})
    assert out["tool_calls"][0]["result"] == expected
    assert "营业额异常记录" in out["answer"]


def test_anomaly_tool_returns_total_and_items():
    result = run_tool("get_sales_anomalies", {})
    assert set(result) == {"total", "items"}
    assert result["total"] == len(result["items"])
    assert result["items"] == detect_sales_anomalies(db.get_store_daily_revenue())


# ---------- 集成测试：真实 DeepSeek（需 DEEPSEEK_API_KEY） ----------

REQUIRES_KEY = "DEEPSEEK_API_KEY" in os.environ


@pytest.mark.integration
@pytest.mark.skipif(not REQUIRES_KEY, reason="未配置 DEEPSEEK_API_KEY")
def test_end_to_end_june_revenue_matches_db():
    out = chat("2026年6月的总营业额是多少元？")
    expected = db.get_summary("2026-06-01", "2026-06-30")["revenue"]
    nums = _extract_numbers(out["answer"])
    assert out["tool_calls"], "季度营业额问题应触发工具查询"
    assert any(abs(n - expected) < 0.01 for n in nums), f"回答数字 {nums} 应含 {expected}"


@pytest.mark.integration
@pytest.mark.skipif(not REQUIRES_KEY, reason="未配置 DEEPSEEK_API_KEY")
def test_end_to_end_anomaly_detection_runs():
    out = chat("最近有哪些门店的营业额出现异常？")
    assert out["tool_calls"]
    tools = {tc["tool"] for tc in out["tool_calls"]}
    assert "get_sales_anomalies" in tools, "异常问题应触发 get_sales_anomalies 工具"