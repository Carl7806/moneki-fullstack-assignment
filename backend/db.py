"""数据库访问层：所有看板 SQL 集中在此，供 API 与 AI 工具复用。"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _date_range(start, end, alias=None):
    col = f"{alias}.date" if alias else "date"
    params = []
    cond = ""
    if start and end:
        cond = f"WHERE {col} BETWEEN ? AND ?"
        params = [start, end]
    elif start:
        cond = f"WHERE {col} >= ?"
        params = [start]
    elif end:
        cond = f"WHERE {col} <= ?"
        params = [end]
    return cond, params


def get_summary(start=None, end=None):
    """总营业额（含退款）、订单数（正金额）、退款额。"""
    conn = get_conn()
    cur = conn.cursor()
    cond, params = _date_range(start, end)
    q = f"""
        SELECT ROUND(SUM(amount), 2) AS revenue,
               COUNT(DISTINCT CASE WHEN amount > 0 THEN order_id END) AS orders,
               ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS refund
        FROM sales {cond}
    """
    cur.execute(q, params)
    row = cur.fetchone()
    conn.close()
    revenue = row["revenue"] or 0.0
    orders = row["orders"] or 0
    refund = row["refund"] or 0.0
    return {
        "revenue": revenue,
        "orders": orders,
        "avg_ticket": round(revenue / orders, 2) if orders else 0.0,
        "refund": refund,
    }


def get_daily(start=None, end=None):
    """每日营业额、订单数、客单价（趋势图）。"""
    conn = get_conn()
    cur = conn.cursor()
    cond, params = _date_range(start, end)
    q = f"""
        SELECT date,
               ROUND(SUM(amount), 2) AS revenue,
               COUNT(DISTINCT CASE WHEN amount > 0 THEN order_id END) AS orders
        FROM sales {cond}
        GROUP BY date
        ORDER BY date
    """
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        revenue = r["revenue"] or 0.0
        orders = r["orders"] or 0
        out.append({
            "date": r["date"],
            "revenue": revenue,
            "orders": orders,
            "avg_ticket": round(revenue / orders, 2) if orders else 0.0,
        })
    return out


def get_top10(start=None, end=None):
    """Top10 商品（按净营业额），JOIN 商品维表取名称/品类。"""
    conn = get_conn()
    cur = conn.cursor()
    cond, params = _date_range(start, end, alias="s")
    q = f"""
        SELECT p.product_name, p.product_category,
               ROUND(SUM(s.amount), 2) AS revenue,
               ROUND(SUM(s.qty), 2) AS qty
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        {cond}
        GROUP BY s.product_id
        ORDER BY revenue DESC
        LIMIT 10
    """
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]