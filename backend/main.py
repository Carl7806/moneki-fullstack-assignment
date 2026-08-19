"""FastAPI 后端：看板数据接口。

启动：uvicorn main:app --reload --port 8000
"""
import re
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
from ai.chat import chat as ai_chat

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


@app.get("/api/dashboard/summary")
def summary(start: str = None, end: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_summary(start, end)


@app.get("/api/dashboard/daily")
def daily(start: str = None, end: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_daily(start, end)


@app.get("/api/dashboard/top10")
def top10(start: str = None, end: str = None):
    try:
        start = _validate_date(start, "start")
        end = _validate_date(end, "end")
    except ValueError as e:
        return {"error": str(e)}, 400
    if start and end and start > end:
        return {"error": "start 不能晚于 end"}, 400
    return db.get_top10(start, end)


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