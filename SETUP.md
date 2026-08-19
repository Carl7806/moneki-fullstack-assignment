# 项目启动与数据清洗说明

> 全栈开发工程师（AI 产品）实操作业 — 连锁餐饮经营看板

## 一、项目结构

```
moneki-fullstack-assignment/
├── data/                  # 原始 CSV（POS 导出的三张表，含脏数据）
│   ├── sales.csv          # 销售流水 ~1.2 万行
│   ├── stores.csv         # 门店维表（5 家店）
│   └── products.csv       # 商品维表（20 个 SKU）
├── backend/               # FastAPI + SQLite
│   ├── etl.py             # 数据清洗 + 建库脚本
│   ├── db.py              # 数据访问层（集中 SQL，供 API 与 AI 工具复用）
│   ├── main.py            # 看板 API 入口
│   ├── requirements.txt   # 后端依赖
│   └── app.db             # etl 生成（已 gitignore，不提交）
└── frontend/              # Vue 3 + Vite + ECharts
    ├── src/
    │   ├── App.vue        # 看板布局 + 日期筛选
    │   ├── api.js         # fetch 封装
    │   └── components/    # KpiCard / RevenueChart / TopProducts
    └── package.json
```

## 二、快速启动（3 步）

### 环境要求

- Python 3.10+
- Node.js 18+（建议 20+）

### 第 1 步：安装后端依赖 + 生成数据库

```bash
pip install -r backend/requirements.txt
python backend/etl.py
```

`etl.py` 会清洗 `data/` 下三张 CSV，生成 `backend/app.db`，并在终端打印清洗报告。

### 第 2 步：启动后端 API

```bash
cd backend
uvicorn main:app --reload --port 8000
```

验证：访问 <http://127.0.0.1:8000/api/health> 应返回 `{"status":"ok"}`。

### 第 3 步：启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173> 即可看到看板（Vite 已将 `/api` 代理到后端 8000 端口）。

---

### 本机环境注意事项（沙箱/Windows 特有问题）

1. **PowerShell 执行策略**：直接敲 `npm` 可能因 `.ps1` 被禁而失败，改用 `npm.cmd install`、`npm.cmd run dev`，或先执行 `Set-ExecutionPolicy -Scope Process Bypass`。

2. **npm 缓存权限**：若 `npm install` 报 `EPERM`（默认缓存指向 `C:\Program Files\nodejs\node_cache` 被限制），显式重定向缓存：

   ```bash
   npm.cmd install --cache "C:\Users\<你的用户名>\AppData\Local\npm-cache"
   ```

## 三、数据清洗说明

生产导出的 POS 数据**不是干净样例**，`sales.csv` 存在 7 类脏数据。以下为实测规模与处理规则。

### 脏数据全貌（实测）

| # | 问题 | 实测规模 | 处理方式 |
|---|---|---|---|
| 1 | 日期格式混用（3 种） | `YYYY-MM-DD` 11981 行、`YYYY/MM/DD` 75 行、`DD-MM-YYYY` 75 行 | 统一归一化为 `YYYY-MM-DD` |
| 2 | 脏外键 | `product_id=P99` 30 行、`store_id=S99` 7 行 | 指向不存在的维度 → 剔除 |
| 3 | 外键大小写 / 空格 | `s01` 小写 9 行、`S01 ` 带空格 4 行 | `strip()` + 统一大写修复 |
| 4 | 金额带货币符号 | `¥66.00` 之类 40 行 | 去 `¥`/`￥` 保留数值 |
| 5 | 负金额（退款） | 49 行 | 保留，营业额统计时自然抵扣 |
| 6 | 数量异常 | `qty=0` 11 行、`qty<0` 14 行 | 用 `amount ÷ unit_price` 反推真实数量 |
| 7 | 金额缺失 | 120 行 | 119 行用 `qty × unit_price` 补齐；1 行因 `P99` 已被剔除 |
| 8 | 重复明细 | 80 组重复 order_id（去重 79 组） | 规范化后完全相同的明细行去重 |

### 清洗规则（与 `etl.py` 一致）

1. **日期归一化**：识别三种格式统一为 `YYYY-MM-DD`，无法识别则剔除。
2. **外键清洗**：`strip()` 去空格 + 统一大写；JOIN 不到维表的脏外键（`S99`/`P99`）剔除。
3. **金额清洗**：去货币符号；负数保留（退款）；空值用 `qty × unit_price` 补齐。
4. **数量修复**：`qty<=0` 但 `amount>0` 且能被 `unit_price` 整除时，反推 `qty = amount / unit_price`。
5. **去重**：以上规范化后完全相同的明细行去重（含日期格式 / 大小写差异导致的伪重复）。

### 清洗结果

```
raw_sales_rows:   12131
drop_bad_product:    30   # P99 脏外键
drop_bad_store:       7   # S99 脏外键
drop_duplicate:      79   # 规范化后重复
fix_qty:             25   # qty=0 / qty<0 反推
fix_amount:         119   # 空金额补齐
clean_sales_rows: 12015   # 12131 - 30 - 7 - 79 = 12015 ✓
日期范围: 2026-05-01 ~ 2026-07-31
```

### 核心指标口径（第二关 AI 取数必须对齐）

| 指标 | 定义 | 说明 |
|---|---|---|
| 营业额 | `SUM(amount)` | 退款（负金额）自然抵扣，得到净营业额 |
| 订单数 | `COUNT(DISTINCT order_id WHERE amount > 0)` | 退款不计为成交订单 |
| 客单价 | `营业额 ÷ 订单数` | —— |
| 退款额 | `SUM(amount WHERE amount < 0)` | 负数合计 |

> 注意：存在 1 组 order_id 相同但 `store_id` 冲突的脏数据（`ORD103779`），因无法判断归属，采取保留处理并将其写入订单数去重口径，金额影响可忽略。