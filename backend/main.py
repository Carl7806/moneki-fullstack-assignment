"""FastAPI 后端：看板数据接口。

启动：uvicorn main:app --reload --port 8000
"""
import re
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
from ai.chat import chat as ai_chat
from ai.chat import chat_stream, sse
from analytics import detect_sales_anomalies

app = FastAPI(title="Moneki 餐饮看板 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value, name):
    if value is not None and not DATE_RE.match(value):
        raise ValueError(f"{name} 格式应为 YYYY-MM-DD")
    return value


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/stores")
def stores():
    return db.get_stores()


@app.get("/api/dashboard/summary")
def summary(start: str = None, end: str = None, store_id: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_summary(start, end, store_id)


@app.get("/api/dashboard/daily")
def daily(start: str = None, end: str = None, store_id: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_daily(start, end, store_id)


@app.get("/api/dashboard/top10")
def top10(start: str = None, end: str = None, store_id: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_top10(start, end, store_id)


@app.get("/api/dashboard/anomalies")
def anomalies(start: str = None, end: str = None, store_id: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    items = detect_sales_anomalies(db.get_store_daily_revenue(start, end, store_id))
    return {"total": len(items), "threshold": 2.0, "items": items}


class ChatRequest(BaseModel):
    message: str
    history: Optional[list[dict]] = None


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    try:
        result = ai_chat(req.message, req.history)
        return result
    except RuntimeError as e:
        return {"error": str(e), "answer": None, "tool_calls": []}, 500


@app.post("/api/chat/stream")
def chat_stream_endpoint(req: ChatRequest):
    def gen():
        try:
            for chunk in chat_stream(req.message, req.history):
                yield chunk
        except RuntimeError as e:
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")