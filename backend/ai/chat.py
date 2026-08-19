"""DeepSeek 编排：意图识别 -> 选工具 -> 执行真实 SQL -> 结果回填 -> 生成回答。

核心原则：数字只来自工具内的数据库查询，LLM 不接触 CSV 原文、不凭记忆回答。
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .tools import TOOLS, run_tool, wants_anomaly_check

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """你是连锁餐饮品牌「Moneki」的运营数据分析助手。你只能基于数据库查询工具返回的真实数据来回答，严禁编造、猜测或凭常识虚报任何数字。

数据背景：
- 时间范围：2026-05-01 到 2026-07-31
- 门店（store_id / 名称 / 经营品类 / 地段）：
  S01 Super Souper（拉面，上海·徐汇）
  S02 Makai Poke（轻食，上海·静安）
  S03 Juicy Bao Bao（点心，上海·浦东）
  S04 Arigato Sando（三明治，上海·长宁）
  S05 Super Tetsudo（日料，上海·黄浦）
- 商品品类：主食、点心、小食、饮料

回答规则：
1. 每个数字都必须来自工具查询结果。工具返回什么就说什么，不得四舍五入虚构、不得外推编造。
2. 相对时间要换算成绝对日期：「六月」= 2026-06-01 到 2026-06-30；「上半年」= 2026-05-01 到 2026-06-30；「最近/近一个月」= 2026-07-01 到 2026-07-31；「全程/总共」= 不传日期。
3. 判断涨跌时，用工具返回的逐日/前后数字对比，明确说「从 X 涨到 Y」或「从 X 跌到 Y」，给出具体数值。
4. 若工具返回空数据，或用户问的是数据里不存在的维度/商品，直接回答「数据里没有相关记录」，不要编造。
5. 用中文回答，简洁直接；金额保留两位小数并带「元」；回答末尾可附一句「以上数据来自数据库实查」。
"""


def _get_client():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 里设置")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def _anomaly_seed(user_message):
    """预警意图确定性触发：直接执行真实 SQL，把结果作为工具消息预注入，
    规避 LLM 对「异常/预警」这类意图的工具选择不稳定，数字仍来自数据库。
    """
    if not wants_anomaly_check(user_message):
        return [], []
    result = run_tool("get_sales_anomalies", {})
    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "anomaly_seed",
            "type": "function",
            "function": {"name": "get_sales_anomalies", "arguments": "{}"},
        }],
    }
    tool_msg = {
        "role": "tool",
        "tool_call_id": "anomaly_seed",
        "content": json.dumps(result, ensure_ascii=False),
    }
    log = [{"tool": "get_sales_anomalies", "args": {}, "result": result}]
    return [assistant_msg, tool_msg], log


def chat(user_message, history=None):
    """执行一次对话。history 为 [{"role":"user"|"assistant","content":...}, ...] 可选。

    返回 {"answer": str, "tool_calls": [{"tool","args","result"}]}
    """
    client = _get_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    seed_msgs, tool_calls_log = _anomaly_seed(user_message)
    messages.extend(seed_msgs)

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return {
                "answer": msg.content or "",
                "tool_calls": tool_calls_log,
            }

        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}
            try:
                result = run_tool(fn_name, fn_args)
            except ValueError as e:
                result = {"error": str(e)}
            tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return {
        "answer": "抱歉，问题需要多次查询仍未收敛，请换个更具体的问题。",
        "tool_calls": tool_calls_log,
    }


def sse(data):
    """把 dict 编码为一条 SSE 事件（data 行 + 空行分隔）。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def chat_stream(user_message, history=None):
    """流式版对话：工具调用阶段非流式（发 status 事件），最终答案逐字流式返回。

    生成的事件类型：
    - {"type": "status", "tool": ..., "args": ...}   开始查询某个工具
    - {"type": "delta", "content": "..."}            答案片段
    - {"type": "done", "tool_calls": [...]}          结束，附带完整工具调用记录
    """
    client = _get_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    seed_msgs, tool_calls_log = _anomaly_seed(user_message)
    if seed_msgs:
        yield sse({"type": "status", "tool": "get_sales_anomalies", "args": {}})
    messages.extend(seed_msgs)

    # 非流式循环：直到模型不再要求调用工具
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            break
        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}
            yield sse({"type": "status", "tool": fn_name, "args": fn_args})
            try:
                result = run_tool(fn_name, fn_args)
            except ValueError as e:
                result = {"error": str(e)}
            tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 流式输出最终答案（不带 tools，避免再次触发工具调用）
    stream = client.chat.completions.create(model=MODEL, messages=messages, stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield sse({"type": "delta", "content": delta.content})

    yield sse({"type": "done", "tool_calls": tool_calls_log})