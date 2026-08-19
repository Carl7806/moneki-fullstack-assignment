"""销售数据分析算法：供 AI 工具与看板接口复用，保证两处的异常检测口径一致。"""
from collections import defaultdict
from statistics import mean, stdev


def detect_sales_anomalies(rows, threshold=2.0):
    """对每家店每日营业额做 z-score 异常检测，返回 |z|>=threshold 的记录（按 |z| 降序）。"""
    by_store = defaultdict(list)
    for r in rows:
        by_store[r["store_name"]].append(r)

    anomalies = []
    for store, recs in by_store.items():
        revenues = [r["revenue"] for r in recs]
        if len(revenues) < 5:
            continue
        mu = mean(revenues)
        sd = stdev(revenues)
        if sd == 0:
            continue
        for r in recs:
            z = (r["revenue"] - mu) / sd
            if abs(z) >= threshold:
                anomalies.append({
                    "store_name": store,
                    "date": r["date"],
                    "revenue": r["revenue"],
                    "z_score": round(z, 2),
                    "deviation": "偏高" if z > 0 else "偏低",
                })
    anomalies.sort(key=lambda x: -abs(x["z_score"]))
    return anomalies