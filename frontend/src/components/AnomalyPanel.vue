<template>
  <div class="anomaly card">
    <div class="anomaly__head">
      <div class="anomaly__title-row">
        <h3 class="anomaly__title">异常销售预警</h3>
        <span v-if="!loading && data.total" class="anomaly__badge">MAD 阈值 {{ data.threshold }}</span>
      </div>
      <div class="anomaly__summary" :class="{ muted: !data.total }">
        <template v-if="loading"><span class="skeleton anomaly__skeleton-text"></span></template>
        <template v-else-if="data.total">检测到 <strong>{{ data.total }}</strong> 条营业额异常记录</template>
        <template v-else>当前区间未检测到营业额异常</template>
      </div>
    </div>

    <div v-if="!loading" class="anomaly__note muted">
      MAD 修正 z-score 检测 · 阈值 {{ data.threshold }} · 每家店至少 {{ data.min_samples }} 天观测才参与检测<template v-if="data.skipped && data.skipped.length">；另有 {{ data.skipped.length }} 家门店因观测天数不足被跳过</template>。
    </div>

    <div v-show="!loading && data.total" class="anomaly__body">
      <div ref="el" class="anomaly__chart"></div>
      <table class="anomaly__table">
        <thead>
          <tr>
            <th>门店</th>
            <th>日期</th>
            <th class="num">营业额</th>
            <th class="num">z-score</th>
            <th>方向</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in data.items" :key="a.store_name + a.date">
            <td class="name">{{ a.store_name }}</td>
            <td class="muted">{{ a.date }}</td>
            <td class="num strong">¥{{ money(a.revenue) }}</td>
            <td class="num">{{ a.z_score }}</td>
            <td><span class="anomaly__tag" :class="tagClass(a.deviation)">{{ a.deviation }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Object, default: () => ({ total: 0, threshold: 3.0, items: [], skipped: [], min_samples: 5 }) },
  loading: { type: Boolean, default: false },
})

const el = ref(null)
let chart = null

const HIGH = '#f59e0b'
const LOW = '#3b82f6'

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function tagClass(deviation) {
  return deviation === '偏高' ? 'anomaly__tag--high' : 'anomaly__tag--low'
}

function render() {
  if (!props.data.total || !el.value) return
  if (!chart && (!el.value.clientWidth || !el.value.clientHeight)) {
    nextTick(render)
    return
  }
  if (!chart) chart = echarts.init(el.value)

  // 取 |z| 最大的前 15 条画条形图，最高 |z| 显示在最上方
  const rows = [...props.data.items]
    .sort((a, b) => Math.abs(b.z_score) - Math.abs(a.z_score))
    .slice(0, 15)
    .reverse()

  chart.setOption({
    grid: { top: 16, left: 8, right: 24, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const item = rows[ps[0].dataIndex]
        return `${item.store_name} ${item.date}<br/>营业额 ¥${money(item.revenue)} · z-score ${item.z_score}`
      },
    },
    xAxis: {
      type: 'value',
      name: 'z-score',
      splitLine: { lineStyle: { color: '#f3f4f6' } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((r) => `${r.store_name} ${r.date.slice(5)}`),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: '60%',
        data: rows.map((r) => ({
          value: r.z_score,
          itemStyle: { color: r.deviation === '偏高' ? HIGH : LOW, borderRadius: [0, 4, 4, 0] },
        })),
      },
    ],
  })
}

function onResize() {
  chart && chart.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart && chart.dispose()
})

watch(() => props.data, render, { deep: true, flush: 'post' })

// total 归零时销毁图表实例，避免下一次空→非空切换时图表还绑在已卸载的旧 DOM 上
watch(() => props.data.total, (t) => {
  if (!t && chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.anomaly__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.anomaly__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.anomaly__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.anomaly__badge {
  font-size: 12px;
  color: var(--brand);
  background: #e9f7f0;
  border-radius: 999px;
  padding: 2px 10px;
}
.anomaly__summary {
  font-size: 13px;
  color: var(--text);
}
.anomaly__summary strong {
  color: var(--danger);
}
.anomaly__skeleton-text {
  display: inline-block;
  width: 200px;
  height: 16px;
}
.anomaly__note {
  font-size: 12px;
  line-height: 1.6;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f9fafb;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.anomaly__chart {
  width: 100%;
  height: 320px;
}
.anomaly__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  margin-top: 8px;
}
.anomaly__table th {
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-2);
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.anomaly__table td {
  padding: 10px;
  border-bottom: 1px solid #f3f4f6;
}
.anomaly__table tr:last-child td {
  border-bottom: none;
}
.name {
  font-weight: 600;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.strong {
  font-weight: 600;
}
.anomaly__tag {
  font-size: 12px;
  border-radius: 6px;
  padding: 2px 8px;
  font-weight: 600;
}
.anomaly__tag--high {
  color: #b45309;
  background: #fef3c7;
}
.anomaly__tag--low {
  color: #1d4ed8;
  background: #dbeafe;
}
</style>