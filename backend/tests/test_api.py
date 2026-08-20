"""API 契约测试：覆盖 /api/dashboard/* 与 /api/chat 端点的参数校验、返回结构与限流。

不联网：AI 相关端点通过 monkeypatch 打桩，其余端点走真实 SQLite 数据。
"""
from fastapi.testclient import TestClient

import main
from ratelimit import SlidingWindowLimiter

client = TestClient(main.app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_summary_shape():
    body = client.get("/api/dashboard/summary").json()
    assert set(body) == {"revenue", "orders", "avg_ticket", "refund"}
    assert body["orders"] > 0


def test_summary_store_filter_narrows_scope():
    all_s = client.get("/api/dashboard/summary").json()
    s01 = client.get("/api/dashboard/summary", params={"store_id": "S01"}).json()
    assert 0 < s01["orders"] < all_s["orders"]
    assert s01["revenue"] < all_s["revenue"]


def test_daily_shape():
    items = client.get("/api/dashboard/daily").json()
    assert items
    assert set(items[0]) == {"date", "revenue", "orders", "avg_ticket"}


def test_top10_sorted_and_limited():
    items = client.get("/api/dashboard/top10").json()
    assert 0 < len(items) <= 10
    revenues = [i["revenue"] for i in items]
    assert revenues == sorted(revenues, reverse=True)
    assert set(items[0]) >= {"product_name", "product_category", "revenue", "qty"}


def test_store_ranking_sorted_desc():
    items = client.get("/api/dashboard/store_ranking").json()
    assert items
    revenues = [i["revenue"] for i in items]
    assert revenues == sorted(revenues, reverse=True)
    assert set(items[0]) >= {"store_name", "category", "district", "revenue", "orders"}


def test_category_ranking_shape():
    items = client.get("/api/dashboard/category_ranking").json()
    assert items
    assert set(items[0]) >= {"product_category", "revenue", "qty"}


def test_anomalies_shape():
    body = client.get("/api/dashboard/anomalies").json()
    assert body["total"] == len(body["items"])
    assert body["threshold"] == 3.0
    assert body["min_samples"] == 5
    assert "skipped" in body
    if body["items"]:
        assert set(body["items"][0]) >= {"store_id", "store_name", "date", "revenue", "z_score", "deviation"}


def test_meta_shape():
    body = client.get("/api/dashboard/meta").json()
    assert set(body) == {"min_date", "max_date", "generated_at"}
    assert body["min_date"]
    assert body["max_date"]
    assert body["generated_at"]


def test_export_returns_csv():
    resp = client.get("/api/dashboard/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "moneki_dashboard_" in resp.headers["content-disposition"]
    text = resp.text
    assert "经营概要" in text
    assert "每日经营趋势" in text
    assert "门店排行" in text


def test_export_invalid_date_returns_400():
    resp = client.get("/api/dashboard/export", params={"start": "2026/01/01"})
    assert resp.status_code == 400


def test_stores_shape():
    items = client.get("/api/dashboard/stores").json()
    assert items
    assert set(items[0]) == {"store_id", "store_name", "category", "district"}


def test_invalid_date_returns_400():
    resp = client.get("/api/dashboard/summary", params={"start": "2026/01/01"})
    assert resp.status_code == 400
    assert "格式" in resp.json()["error"]


def test_start_after_end_returns_400():
    resp = client.get("/api/dashboard/summary", params={"start": "2026-07-31", "end": "2026-07-01"})
    assert resp.status_code == 400
    assert "晚于" in resp.json()["error"]


def test_chat_rate_limited(monkeypatch):
    monkeypatch.setattr(main, "chat_limiter", SlidingWindowLimiter(max_requests=2, window_seconds=60))
    monkeypatch.setattr(main, "ai_chat", lambda m, h: {"answer": "ok", "tool_calls": [], "focus": None})

    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 429
    assert "频繁" in resp.json()["error"]


def test_chat_message_too_long():
    resp = client.post("/api/chat", json={"message": "x" * (main.MAX_MESSAGE_LENGTH + 1)})
    assert resp.status_code == 400
    assert "过长" in resp.json()["error"]


def test_chat_stream_message_too_long():
    resp = client.post("/api/chat/stream", json={"message": "x" * (main.MAX_MESSAGE_LENGTH + 1)})
    assert resp.status_code == 200
    assert "过长" in resp.text