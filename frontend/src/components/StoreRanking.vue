<template>
  <div class="store card">
    <h3 class="store__title">门店排行</h3>
    <div class="store__wrap">
      <div ref="el" class="store__body"></div>
      <div v-if="loading" class="store__overlay">
        <span class="skeleton store__skeleton"></span>
      </div>
      <div v-else-if="!data.length" class="store__empty muted">暂无数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const el = ref(null)
let chart = null

function render() {
  if (!el.value || !props.data.length) return
  if (!chart) chart = echarts.init(el.value)

  // 按营业额升序排列，最高的显示在最上方
  const rows = [...props.data].sort((a, b) => a.revenue - b.revenue)

  chart.setOption({
    grid: { top: 8, left: 8, right: 40, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const r = rows[ps[0].dataIndex]
        return `${r.store_name}<br/>品类：${r.category} · ${r.district}<br/>营业额 ¥${r.revenue.toLocaleString()} · 订单 ${r.orders.toLocaleString()}`
      },
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f3f4f6' } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((r) => r.store_name),
      axisLine: { lineStyle: { color: '#d1d5db' } },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: '56%',
        data: rows.map((r) => ({
          value: r.revenue,
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#057a55' },
              { offset: 1, color: '#34d399' },
            ]),
          },
        })),
        label: {
          show: true,
          position: 'right',
          formatter: (p) => '¥' + Number(p.value).toLocaleString(),
          color: '#6b7280',
          fontSize: 12,
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
</script>

<style scoped>
.store__title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}
.store__wrap {
  position: relative;
}
.store__body {
  width: 100%;
  height: 300px;
}
.store__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.store__overlay {
  position: absolute;
  inset: 0;
  background: #fff;
  border-radius: 8px;
  padding: 8px;
}
.store__skeleton {
  display: block;
  width: 100%;
  height: 100%;
}
</style>