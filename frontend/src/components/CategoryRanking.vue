<template>
  <div class="cat card">
    <h3 class="cat__title">品类构成</h3>
    <div class="cat__wrap">
      <div ref="el" class="cat__body"></div>
      <div v-if="!data.length" class="cat__empty muted">暂无数据</div>
    </div>
    <ul v-if="data.length" class="cat__legend">
      <li v-for="c in data" :key="c.product_category" class="cat__legend-item">
        <span class="cat__dot" :style="{ background: color(c.product_category) }"></span>
        <span class="cat__name">{{ c.product_category }}</span>
        <span class="cat__val">¥{{ c.revenue.toLocaleString() }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const el = ref(null)
let chart = null

const PALETTE = ['#0e9f6e', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444', '#14b8a6']
const color = (name) => PALETTE[props.data.findIndex((d) => d.product_category === name) % PALETTE.length]

function render() {
  if (!el.value || !props.data.length) return
  if (!chart) chart = echarts.init(el.value)

  chart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}<br/>营业额 ¥${Number(p.value).toLocaleString()}（${p.percent}%）`,
    },
    legend: { show: false },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: {
          formatter: '{b}\n{d}%',
          color: '#6b7280',
          fontSize: 12,
        },
        data: props.data.map((d) => ({ name: d.product_category, value: d.revenue })),
        color: PALETTE,
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
</script>

<style scoped>
.cat__title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}
.cat__wrap {
  position: relative;
}
.cat__body {
  width: 100%;
  height: 240px;
}
.cat__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cat__legend {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}
.cat__legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.cat__dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}
.cat__name {
  color: var(--text);
}
.cat__val {
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
</style>