"""FastAPI 后端：看板数据接口。

启动：uvicorn main:app --reload --port 8000
"""
import csv
import io
import re
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel

import db
from ai.chat import chat as ai_chat
from ai.chat import chat_stream, sse
from analytics import detect_sales_anomalies_with_meta, DEFAULT_THRESHOLD
from ratelimit import SlidingWindowLimiter

app = FastAPI(title="Moneki 餐饮看板 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# AI 问答接口防护：限流 + 长度上限
CHAT_RATE_MAX = 20          # 每个客户端 IP 每分钟最多请求数
CHAT_RATE_WINDOW = 60       # 滑动窗口秒数
MAX_MESSAGE_LENGTH = 2000   # 单条问题最大字符数

chat_limiter = SlidingWindowLimiter(CHAT_RATE_MAX, CHAT_RATE_WINDOW)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _validate_date(value, name):
    if value is not None and not DATE_RE.match(value):
        raise ValueError(f"{name} 格式应为 YYYY-MM-DD")
    return value


def _parse_range(start, end):
    """校验 start/end 日期参数，返回 (start, end, 错误响应或 None)。"""
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return None, None, JSONResponse({"error": str(e)}, status_code=400)
    if start and end and start > end:
        return None, None, JSONResponse({"error": "start 不能晚于 end"}, status_code=400)
    return start, end, None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/meta")
def meta():
    """数据集元信息：最早/最晚交易日期、ETL 最后运行时间。"""
    return db.get_data_meta()


@app.get("/api/dashboard/stores")
def stores():
    return db.get_stores()


@app.get("/api/dashboard/summary")
def summary(start: str = None, end: str = None, store_id: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    return db.get_summary(start, end, store_id)


@app.get("/api/dashboard/daily")
def daily(start: str = None, end: str = None, store_id: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    return db.get_daily(start, end, store_id)


@app.get("/api/dashboard/top10")
def top10(start: str = None, end: str = None, store_id: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    return db.get_top10(start, end, store_id)


@app.get("/api/dashboard/store_ranking")
def store_ranking(start: str = None, end: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    return db.get_store_ranking(start, end)


@app.get("/api/dashboard/category_ranking")
def category_ranking(start: str = None, end: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    return db.get_category_ranking(start, end)


@app.get("/api/dashboard/anomalies")
def anomalies(start: str = None, end: str = None, store_id: str = None):
    start, end, err = _parse_range(start, end)
    if err:
        return err
    result = detect_sales_anomalies_with_meta(db.get_store_daily_revenue(start, end, store_id))
    return {
        "total": len(result["items"]),
        "threshold": DEFAULT_THRESHOLD,
        "items": result["items"],
        "skipped": result["skipped"],
        "min_samples": result["min_samples"],
    }


@app.get("/api/dashboard/export")
def export(start: str = None, end: str = None, store_id: str = None):
    """导出当前筛选区间的汇总数据为 CSV（概要 + 每日趋势 + 门店/品类排行 + Top10）。"""
    start, end, err = _parse_range(start, end)
    if err:
        return err

    summary = db.get_summary(start, end, store_id)
    daily = db.get_daily(start, end, store_id)
    store_rank = db.get_store_ranking(start, end)
    category_rank = db.get_category_ranking(start, end)
    top = db.get_top10(start, end, store_id)

    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["经营概要"])
    w.writerow(["总营业额", summary["revenue"]])
    w.writerow(["订单数", summary["orders"]])
    w.writerow(["客单价", summary["avg_ticket"]])
    w.writerow(["退款额", summary["refund"]])
    w.writerow([])

    w.writerow(["每日经营趋势"])
    w.writerow(["日期", "营业额", "订单数", "客单价"])
    for d in daily:
        w.writerow([d["date"], d["revenue"], d["orders"], d["avg_ticket"]])
    w.writerow([])

    w.writerow(["门店排行"])
    w.writerow(["门店", "品类", "地段", "营业额", "订单数"])
    for s in store_rank:
        w.writerow([s["store_name"], s["category"], s["district"], s["revenue"], s["orders"]])
    w.writerow([])

    w.writerow(["品类构成"])
    w.writerow(["品类", "营业额", "销量"])
    for c in category_rank:
        w.writerow([c["product_category"], c["revenue"], c["qty"]])
    w.writerow([])

    w.writerow(["Top 10 商品"])
    w.writerow(["商品", "品类", "销量", "营业额"])
    for p in top:
        w.writerow([p["product_name"], p["product_category"], p["qty"], p["revenue"]])

    content = "\ufeff" + buf.getvalue()  # UTF-8 BOM，便于 Excel 识别中文
    filename = f"moneki_dashboard_{start or 'all'}_{end or 'all'}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ChatRequest(BaseModel):
    message: str
    history: Optional[list[dict]] = None


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest, request: Request):
    if not chat_limiter.allow(_client_ip(request)):
        return JSONResponse({"error": "请求过于频繁，请稍后再试", "answer": None, "tool_calls": []}, status_code=429)
    if len(req.message) > MAX_MESSAGE_LENGTH:
        return JSONResponse({"error": f"问题过长（最多 {MAX_MESSAGE_LENGTH} 字符）", "answer": None, "tool_calls": []}, status_code=400)
    try:
        result = ai_chat(req.message, req.history)
        return result
    except RuntimeError as e:
        return JSONResponse({"error": str(e), "answer": None, "tool_calls": []}, status_code=500)


@app.post("/api/chat/stream")
def chat_stream_endpoint(req: ChatRequest, request: Request):
    if not chat_limiter.allow(_client_ip(request)):
        def _limited():
            yield sse({"type": "error", "message": "请求过于频繁，请稍后再试"})
        return StreamingResponse(_limited(), media_type="text/event-stream")

    if len(req.message) > MAX_MESSAGE_LENGTH:
        def _too_long():
            yield sse({"type": "error", "message": f"问题过长（最多 {MAX_MESSAGE_LENGTH} 字符）"})
        return StreamingResponse(_too_long(), media_type="text/event-stream")

    def gen():
        try:
            for chunk in chat_stream(req.message, req.history):
                yield chunk
        except RuntimeError as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")