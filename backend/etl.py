"""ETL: 清洗 POS 导出的三张 CSV 并建 SQLite 库。

清洗规则（详见 README.md「数据清洗」章节）：
1. 日期归一化：支持 YYYY-MM-DD / YYYY/MM/DD / DD-MM-YYYY 三种格式
2. 外键清洗：store_id 去空格 + 统一大写；指向不存在门店/商品的脏外键剔除
3. 金额清洗：去掉 ¥/￥ 货币符号；负数保留（退款）；空值用 qty * unit_price 补齐
4. 数量修复：qty<=0 但 amount>0 且能被 unit_price 整除时，用 amount/unit_price 反推
5. 去重：规范化后完全相同的明细行去重（含日期/大小写差异导致的伪重复）

运行：python backend/etl.py
"""
import csv
import sqlite3
import os
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_PATH = os.path.join(BASE_DIR, "app.db")

VALID_STORES = {"S01", "S02", "S03", "S04", "S05"}


def parse_date(raw: str):
    """归一化日期为 YYYY-MM-DD，无法识别返回 None。"""
    s = raw.strip()
    if not s:
        return None
    if "/" in s:
        return s.replace("/", "-")
    parts = s.split("-")
    if len(parts) != 3:
        return None
    if parts[0] == "2026":
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    if parts[2] == "2026":
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return None


def parse_amount(raw: str):
    """解析金额：去货币符号，负数保留（退款），空值返回 None。"""
    s = raw.strip()
    if not s:
        return None
    s = s.replace("¥", "").replace("￥", "").strip()
    return float(s)


def load_csv(name):
    path = os.path.join(DATA_DIR, name)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean_sales(raw_rows, product_price, stats):
    cleaned = []
    seen = set()
    for r in raw_rows:
        order_id = r["order_id"].strip()
        date = parse_date(r["date"])
        store_id = r["store_id"].strip().upper()
        product_id = r["product_id"].strip().upper()
        qty_raw = r["qty"].strip()
        amount_raw = r["amount"].strip()
        payment = r["payment"].strip()

        if date is None:
            stats["drop_bad_date"] += 1
            continue

        # 脏外键剔除
        if store_id not in VALID_STORES:
            stats["drop_bad_store"] += 1
            continue
        if product_id not in product_price:
            stats["drop_bad_product"] += 1
            continue

        unit_price = product_price[product_id]

        # qty 解析
        try:
            qty = float(qty_raw)
        except ValueError:
            stats["drop_bad_qty"] += 1
            continue

        # amount 解析
        try:
            amount = parse_amount(amount_raw)
        except ValueError:
            stats["drop_bad_amount"] += 1
            continue

        # qty<=0 但金额为正且为单价整数倍 -> 反推真实数量
        if qty <= 0 and amount is not None and amount > 0 and unit_price > 0:
            recovered = amount / unit_price
            if recovered > 0 and abs(recovered - round(recovered)) < 1e-6:
                stats["fix_qty"] += 1
                qty = recovered

        # amount 缺失 -> qty * unit_price
        if amount is None:
            amount = qty * unit_price
            stats["fix_amount"] += 1

        # 修复后数量仍非正 -> 无法判断，剔除
        if qty <= 0:
            stats["drop_unrecoverable"] += 1
            continue

        row = (order_id, date, store_id, product_id, qty, amount, payment)

        # 去重：规范化后完全相同的明细行
        if row in seen:
            stats["drop_duplicate"] += 1
            continue
        seen.add(row)

        cleaned.append(row)
    return cleaned


def run():
    stats = Counter()
    stores = load_csv("stores.csv")
    products = load_csv("products.csv")
    sales = load_csv("sales.csv")

    # 商品 unit_price 映射（清洗金额用）
    product_price = {}
    for p in products:
        try:
            product_price[p["product_id"].strip()] = float(p["unit_price"])
        except ValueError:
            product_price[p["product_id"].strip()] = 0.0

    stats["raw_sales_rows"] = len(sales)
    clean_rows = clean_sales(sales, product_price, stats)
    stats["clean_sales_rows"] = len(clean_rows)

    # 建库
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT)")
    cur.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT, product_category TEXT, unit_price REAL)")
    cur.execute(
        """CREATE TABLE sales (
            order_id TEXT,
            date TEXT,
            store_id TEXT,
            product_id TEXT,
            qty REAL,
            amount REAL,
            payment TEXT
        )"""
    )
    cur.execute("CREATE INDEX idx_sales_date ON sales(date)")
    cur.execute("CREATE INDEX idx_sales_store ON sales(store_id)")
    cur.execute("CREATE INDEX idx_sales_product ON sales(product_id)")

    for s in stores:
        cur.execute(
            "INSERT INTO stores VALUES (?,?,?,?)",
            (s["store_id"].strip(), s["store_name"].strip(), s["category"].strip(), s["district"].strip()),
        )
    for p in products:
        cur.execute(
            "INSERT INTO products VALUES (?,?,?,?)",
            (p["product_id"].strip(), p["product_name"].strip(), p["product_category"].strip(), float(p["unit_price"])),
        )
    cur.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?)", clean_rows)

    conn.commit()
    conn.close()

    print("=== ETL 清洗报告 ===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    # 日期范围
    dates = sorted({r[1] for r in clean_rows})
    print(f"日期范围: {dates[0]} ~ {dates[-1]}")
    print(f"数据库已生成: {DB_PATH}")


if __name__ == "__main__":
    run()