"""AI 工具集：function calling 的 schema 定义 + 统一分发执行。

所有工具都走真实 SQL（见 db.py），LLM 只负责选工具、传参，
数字一律来自数据库查询结果，绝不编造。
"""
import re

import db
from analytics import detect_sales_anomalies

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ANOMALY_KEYWORDS = ("异常", "预警", "突变", "突增", "突降", "飙升", "暴跌", "波动", "异动")


def wants_anomaly_check(text):
    """判断用户是否在询问异常/预警类问题（关键词确定性触发，保证预警功能稳定可用）。"""
    return bool(text) and any(k in text for k in ANOMALY_KEYWORDS)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_revenue_summary",
            "description": (
                "查询指定日期范围的营业额、订单数、客单价、退款额汇总。"
                "适合回答「这个月/上半年营业额多少」「订单量多少」「客单价是多少」等总体问题。"
                "可选按门店过滤，回答「某家店营业额多少」时传入 store_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                    "store_id": {"type": "string", "description": "门店ID，如 S01，可选"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_ranking",
            "description": (
                "查询各门店营业额排行（含门店名称、经营品类、地段、营业额、订单数，按营业额降序）。"
                "适合回答「哪个门店/哪个品类的门店营业额最高」「哪家店卖得最好」等排行比较问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_ranking",
            "description": (
                "查询各商品品类（主食/点心/小食/饮料）的营业额排行，按营业额降序。"
                "适合回答「哪个商品品类卖得最好/营业额最高」等品类比较问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_sales",
            "description": (
                "按商品名（模糊匹配）查询单品销量与营业额。"
                "适合回答「牛肉poke 卖了多少钱」「三文鱼poke 销量多少」等单品问题。"
                "注意可能命中多个商品（如「三明治」），需在回答中说明。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "商品名关键词，如 牛肉poke"},
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                    "store_id": {"type": "string", "description": "门店ID，如 S01（回答「某家店xxx」时传入），可选"},
                },
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_trend",
            "description": (
                "查询每日营业额、订单数、客单价趋势（按日期升序）。"
                "适合回答「客单价最近涨了还是跌了」「营业额趋势如何」等趋势类问题。"
                "拿到逐日数据后自行比较前后变化再下结论。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                    "store_id": {"type": "string", "description": "门店ID，如 S01（回答「某家店xxx」时传入），可选"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_anomalies",
            "description": (
                "检测各门店每日营业额异常（z-score：当日营业额偏离该店历史均值超过 2 个标准差）。"
                "适合回答「哪家店最近销量/营业额有异常」「有没有数据异常」等预警类问题。"
                "返回 {total: 异常条数, items: 异常明细}，回答案时直接引用 total，不要自行数 items。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD，可选"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD，可选"},
                    "store_id": {"type": "string", "description": "门店ID，如 S01（回答「某家店xxx」时传入），可选"},
                },
            },
        },
    },
]


def _valid_date(value, name):
    if value is None:
        return None
    if not DATE_RE.match(value):
        raise ValueError(f"{name} 格式应为 YYYY-MM-DD，收到：{value!r}")
    return value


def _check_range(start, end):
    start = _valid_date(start, "start_date")
    end = _valid_date(end, "end_date")
    if start and end and start > end:
        raise ValueError(f"start_date({start}) 不能晚于 end_date({end})")
    return start, end


def run_tool(name, args):
    """执行工具，返回其结果（list/dict）。参数错误抛 ValueError 交给编排层回给 LLM。"""
    args = args or {}
    if name == "get_revenue_summary":
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        store_id = args.get("store_id")
        return db.get_summary(start, end, store_id)

    if name == "get_store_ranking":
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        return db.get_store_ranking(start, end)

    if name == "get_category_ranking":
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        return db.get_category_ranking(start, end)

    if name == "get_product_sales":
        product_name = (args.get("product_name") or "").strip()
        if not product_name:
            raise ValueError("product_name 不能为空")
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        return db.get_product_sales(product_name, start, end, args.get("store_id"))

    if name == "get_daily_trend":
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        return db.get_daily(start, end, args.get("store_id"))

    if name == "get_sales_anomalies":
        start, end = _check_range(args.get("start_date"), args.get("end_date"))
        items = detect_sales_anomalies(db.get_store_daily_revenue(start, end, args.get("store_id")))
        return {"total": len(items), "items": items}

    raise ValueError(f"未知工具：{name}")