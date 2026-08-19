"""数据库访问层：所有看板 SQL 集中在此，供 API 与 AI 工具复用。"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_all(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def _fetch_one(query, params=()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    conn.close()
    return row


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


def get_summary(start=None, end=None, store_id=None):
    """总营业额（含退款）、订单数（正金额）、退款额，可选门店过滤。"""
    cond, params = _date_range(start, end)
    if store_id:
        cond = f"{cond} AND store_id = ?" if cond else "WHERE store_id = ?"
        params = list(params) + [store_id]
    q = f"""
        SELECT ROUND(SUM(amount), 2) AS revenue,
               COUNT(DISTINCT CASE WHEN amount > 0 THEN order_id END) AS orders,
               ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS refund
        FROM sales {cond}
    """
    row = _fetch_one(q, params)
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
    cond, params = _date_range(start, end)
    q = f"""
        SELECT date,
               ROUND(SUM(amount), 2) AS revenue,
               COUNT(DISTINCT CASE WHEN amount > 0 THEN order_id END) AS orders
        FROM sales {cond}
        GROUP BY date
        ORDER BY date
    """
    rows = _fetch_all(q, params)
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
    return [dict(r) for r in _fetch_all(q, params)]


def get_store_ranking(start=None, end=None):
    """各门店营业额排行（JOIN 门店表取经营品类/地段）。"""
    cond, params = _date_range(start, end, alias="s")
    q = f"""
        SELECT st.store_name, st.category, st.district,
               ROUND(SUM(s.amount), 2) AS revenue,
               COUNT(DISTINCT CASE WHEN s.amount > 0 THEN s.order_id END) AS orders
        FROM sales s
        JOIN stores st ON s.store_id = st.store_id
        {cond}
        GROUP BY s.store_id
        ORDER BY revenue DESC
    """
    return [dict(r) for r in _fetch_all(q, params)]


def get_category_ranking(start=None, end=None):
    """各商品品类营业额排行（JOIN 商品表取品类）。"""
    cond, params = _date_range(start, end, alias="s")
    q = f"""
        SELECT p.product_category,
               ROUND(SUM(s.amount), 2) AS revenue,
               ROUND(SUM(s.qty), 2) AS qty
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        {cond}
        GROUP BY p.product_category
        ORDER BY revenue DESC
    """
    return [dict(r) for r in _fetch_all(q, params)]


def get_product_sales(product_name, start=None, end=None):
    """单品销售查询：先精确匹配商品名，再模糊匹配（可能存在多商品命中）。"""
    cond_date, params = _date_range(start, end, alias="s")
    if cond_date:
        cond_date = cond_date.replace("WHERE", "AND", 1)

    cond_name = "AND p.product_name LIKE ?"
    conds = [cond_date, cond_name] if cond_date else [cond_name]
    params = params + [f"%{product_name}%"]

    q = f"""
        SELECT p.product_name, p.product_category, p.unit_price,
               ROUND(SUM(s.amount), 2) AS revenue,
               ROUND(SUM(s.qty), 2) AS qty,
               COUNT(DISTINCT CASE WHEN s.amount > 0 THEN s.order_id END) AS orders
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        WHERE 1=1 {" ".join(conds)}
        GROUP BY p.product_id
        ORDER BY revenue DESC
    """
    return [dict(r) for r in _fetch_all(q, params)]


def get_store_daily_revenue(start=None, end=None):
    """每家店每日营业额（供异常检测与趋势分析）。"""
    cond, params = _date_range(start, end, alias="s")
    q = f"""
        SELECT st.store_name, s.date, ROUND(SUM(s.amount), 2) AS revenue
        FROM sales s
        JOIN stores st ON s.store_id = st.store_id
        {cond}
        GROUP BY s.store_id, s.date
        ORDER BY s.store_id, s.date
    """
    return [dict(r) for r in _fetch_all(q, params)]