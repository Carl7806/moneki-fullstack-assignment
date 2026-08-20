"""销售数据分析算法：供 AI 工具与看板接口复用，保证两处的异常检测口径一致。

异常检测采用修正 z-score（中位数 + MAD），对离群点本身不敏感，
避免均值/标准差被异常值拉高而导致漏报（masking effect）。
"""
from collections import defaultdict
from statistics import median, stdev

# 修正 z-score 的离群阈值：经典建议 3.5，这里用 3.0 让预警面板覆盖更多中高异常
DEFAULT_THRESHOLD = 3.0

# 使 MAD 在正态分布下与标准差可比（约 1.4826 的倒数）
SCALE_FACTOR = 0.6745


def _median_and_mad(values):
    med = median(values)
    mad = median(abs(x - med) for x in values)
    return med, mad


def detect_sales_anomalies(rows, threshold=DEFAULT_THRESHOLD):
    """对每家店每日营业额做 MAD 修正 z-score 异常检测。

    rows 每条需含 store_id / store_name / date / revenue 字段。
    返回 |z| >= threshold 的记录（按 |z| 降序）。
    """
    by_store = defaultdict(list)
    for r in rows:
        by_store[r["store_id"]].append(r)

    anomalies = []
    for store_id, recs in by_store.items():
        revenues = [r["revenue"] for r in recs]
        if len(revenues) < 5:
            continue
        med, mad = _median_and_mad(revenues)
        # MAD 为 0（过半观测都等于中位数）时退化到标准差尺度，避免除 0
        use_mad = mad > 0
        scale = mad if use_mad else stdev(revenues)
        factor = SCALE_FACTOR if use_mad else 1.0
        if scale == 0:
            continue
        for r in recs:
            z = factor * (r["revenue"] - med) / scale
            if abs(z) >= threshold:
                anomalies.append({
                    "store_id": store_id,
                    "store_name": r["store_name"],
                    "date": r["date"],
                    "revenue": r["revenue"],
                    "z_score": round(z, 2),
                    "deviation": "偏高" if z > 0 else "偏低",
                })
    anomalies.sort(key=lambda x: -abs(x["z_score"]))
    return anomalies