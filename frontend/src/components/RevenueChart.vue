<template>
  <div class="chart card">
    <div class="chart__head">
      <h3 class="chart__title">经营趋势</h3>
      <div class="chart__tabs">
        <button
          v-for="m in metrics"
          :key="m.key"
          class="chart__tab"
          :class="{ 'chart__tab--active': metric === m.key }"
          @click="metric = m.key"
        >
          {{ m.label }}
        </button>
      </div>
    </div>
    <div ref="el" class="chart__body"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const el = ref(null)
const metric = ref('revenue')
let chart = null

const metrics = [
  { key: 'revenue', label: '营业额' },
  { key: 'orders', label: '订单数' },
  { key: 'avg_ticket', label: '客单价' },
]

const metricMeta = {
  revenue: { name: '营业额', unit: '元', color: '#0e9f6e' },
  orders: { name: '订单数', unit: '单', color: '#3b82f6' },
  avg_ticket: { name: '客单价', unit: '元', color: '#f59e0b' },
}

function render() {
  if (!props.data.length) return
  if (!chart) chart = echarts.init(el.value)
  const meta = metricMeta[metric.value]
  chart.setOption({
    grid: { top: 30, left: 12, right: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => `${v} ${meta.unit}`,
    },
    xAxis: {
      type: 'category',
      data: props.data.map((d) => d.date.slice(5)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f3f4f6' } },
      axisLabel: { formatter: `{value}` },
    },
    series: [
      {
        name: meta.name,
        type: 'line',
        smooth: true,
        data: props.data.map((d) => d[metric.value]),
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { width: 2.5, color: meta.color },
        itemStyle: { color: meta.color },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: `${meta.color}33` },
            { offset: 1, color: `${meta.color}00` },
          ]),
        },
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

watch(() => props.data, render, { deep: true })
watch(metric, render)
</script>

<style scoped>
.chart__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.chart__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.chart__tabs {
  display: flex;
  gap: 6px;
  background: #f3f4f6;
  border-radius: 8px;
  padding: 3px;
}
.chart__tab {
  border: none;
  background: transparent;
  padding: 5px 12px;
  font-size: 13px;
  border-radius: 6px;
  color: var(--text-2);
}
.chart__tab--active {
  background: #fff;
  color: var(--text);
  font-weight: 600;
  box-shadow: var(--shadow);
}
.chart__body {
  width: 100%;
  height: 320px;
}
</style>