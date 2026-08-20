<template>
  <div class="dashboard">
    <header class="header">
      <div>
        <h1 class="header__title">Moneki 连锁餐饮经营看板</h1>
        <p class="header__sub muted">5 家门店 · POS 销售流水 · 数据区间 2026-05 ~ 2026-07</p>
      </div>
    </header>

    <div class="filter card">
      <label class="filter__field">
        <span>开始日期</span>
        <input type="date" v-model="start" :max="end" />
      </label>
      <span class="filter__sep">—</span>
      <label class="filter__field">
        <span>结束日期</span>
        <input type="date" v-model="end" :min="start" />
      </label>
      <label class="filter__field">
        <span>门店</span>
        <select v-model="storeId" class="filter__select">
          <option value="">全部门店</option>
          <option v-for="s in stores" :key="s.store_id" :value="s.store_id">{{ s.store_name }}</option>
        </select>
      </label>
      <div class="filter__quick">
        <button
          v-for="q in quickRanges"
          :key="q.label"
          class="filter__btn"
          :class="{ 'filter__btn--active': isQuickActive(q) }"
          @click="applyQuick(q)"
        >
          {{ q.label }}
        </button>
      </div>
      <div class="filter__link" v-if="linked">
        <span>已联动至：{{ linked }}</span>
        <button class="filter__link-clear" @click="clearLink">重置</button>
      </div>
      <div class="filter__error" v-if="error">{{ error }}</div>
    </div>

    <div class="kpis">
      <KpiCard label="总营业额" :value="fmtMoney(summary.revenue)" sub="含退款抵扣" />
      <KpiCard label="订单数" :value="fmtNum(summary.orders)" sub="正金额订单" />
      <KpiCard label="客单价" :value="'¥' + (summary.avg_ticket ?? 0)" sub="营业额 / 订单数" />
      <KpiCard label="退款额" :value="fmtMoney(summary.refund)" sub="负金额合计" danger />
    </div>

    <RevenueChart :data="daily" />

    <TopProducts :data="top10" />

    <div class="rankings">
      <StoreRanking :data="storeRanking" />
      <CategoryRanking :data="categoryRanking" />
    </div>

    <AnomalyPanel :data="anomalies" />

    <ChatPanel @focus="onFocus" />
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import KpiCard from './components/KpiCard.vue'
import RevenueChart from './components/RevenueChart.vue'
import TopProducts from './components/TopProducts.vue'
import StoreRanking from './components/StoreRanking.vue'
import CategoryRanking from './components/CategoryRanking.vue'
import AnomalyPanel from './components/AnomalyPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import { fetchSummary, fetchDaily, fetchTop10, fetchAnomalies, fetchStores, fetchStoreRanking, fetchCategoryRanking } from './api.js'

const DATA_START = '2026-05-01'
const DATA_END = '2026-07-31'

const start = ref(DATA_START)
const end = ref(DATA_END)
const storeId = ref('')
const stores = ref([])
const linked = ref(null)
const suppress = ref(false)
const summary = reactive({ revenue: 0, orders: 0, avg_ticket: 0, refund: 0 })
const daily = ref([])
const top10 = ref([])
const storeRanking = ref([])
const categoryRanking = ref([])
const anomalies = reactive({ total: 0, threshold: 3.0, items: [] })
const error = ref('')

const quickRanges = [
  { label: '近7天', start: '2026-07-25', end: DATA_END },
  { label: '近30天', start: '2026-07-02', end: DATA_END },
  { label: '全部', start: DATA_START, end: DATA_END },
]

function fmtMoney(v) {
  return '¥' + Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}
function fmtNum(v) {
  return Number(v || 0).toLocaleString('zh-CN')
}

function applyQuick(q) {
  start.value = q.start
  end.value = q.end
}

function isQuickActive(q) {
  return start.value === q.start && end.value === q.end
}

function storeName(id) {
  const s = stores.value.find((x) => x.store_id === id)
  return s ? s.store_name : id
}

async function load() {
  error.value = ''
  const params = { start: start.value, end: end.value }
  if (storeId.value) params.store_id = storeId.value
  try {
    const [s, d, t, a, sr, cr] = await Promise.all([
      fetchSummary(params),
      fetchDaily(params),
      fetchTop10(params),
      fetchAnomalies(params),
      fetchStoreRanking(params),
      fetchCategoryRanking(params),
    ])
    Object.assign(summary, s)
    daily.value = d
    top10.value = t
    storeRanking.value = sr
    categoryRanking.value = cr
    Object.assign(anomalies, a)
  } catch (e) {
    error.value = e.message || '加载失败'
  }
}

function onFocus(focus) {
  if (!focus) return
  const s = focus.start_date || start.value
  const e = focus.end_date || end.value
  const sid = focus.store_id || ''
  if (s === start.value && e === end.value && sid === storeId.value) return
  suppress.value = true
  start.value = s
  end.value = e
  storeId.value = sid
  suppress.value = false
  linked.value = `${s} ~ ${e}` + (sid ? ` · ${storeName(sid)}` : '')
  load()
}

function clearLink() {
  linked.value = null
  suppress.value = true
  start.value = DATA_START
  end.value = DATA_END
  storeId.value = ''
  suppress.value = false
  load()
}

watch([start, end, storeId], () => {
  if (suppress.value) return
  linked.value = null
  if (start.value && end.value) load()
})

onMounted(async () => {
  try {
    stores.value = await fetchStores()
  } catch (e) {
    /* 门店列表加载失败不阻塞看板 */
  }
  load()
})
</script>

<style scoped>
.header {
  margin-bottom: 20px;
}
.header__title {
  margin: 0 0 4px;
  font-size: 24px;
  font-weight: 700;
}
.header__sub {
  margin: 0;
  font-size: 13px;
}

.filter {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
  position: relative;
}
.filter__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--text-2);
}
.filter__field input,
.filter__field select {
  font-family: inherit;
  font-size: 14px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text);
}
.filter__select {
  min-width: 140px;
  cursor: pointer;
}
.filter__sep {
  color: var(--text-2);
  padding-bottom: 8px;
}
.filter__quick {
  display: flex;
  gap: 6px;
  padding-bottom: 2px;
}
.filter__btn {
  border: 1px solid var(--border);
  background: #fff;
  padding: 8px 14px;
  font-size: 13px;
  border-radius: 8px;
  color: var(--text-2);
}
.filter__btn--active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}
.filter__link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--brand, #0e9f6e);
  background: rgba(14, 159, 110, 0.08);
  border: 1px solid rgba(14, 159, 110, 0.25);
  border-radius: 8px;
}
.filter__link-clear {
  border: none;
  background: transparent;
  color: var(--brand, #0e9f6e);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}
.filter__error {
  width: 100%;
  color: var(--danger);
  font-size: 13px;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.kpis > * {
  width: 100%;
}

.rankings {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.dashboard .chart {
  margin-bottom: 20px;
}

@media (max-width: 760px) {
  .kpis {
    grid-template-columns: repeat(2, 1fr);
  }
  .rankings {
    grid-template-columns: 1fr;
  }
}
</style>