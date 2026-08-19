<template>
  <div class="top card">
    <h3 class="top__title">Top 10 商品</h3>
    <div v-if="!data.length" class="muted top__empty">暂无数据</div>
    <table v-else class="top__table">
      <thead>
        <tr>
          <th class="rank">#</th>
          <th>商品</th>
          <th>品类</th>
          <th class="num">销量</th>
          <th class="num">营业额</th>
          <th class="bar-col">占比</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(p, i) in data" :key="p.product_name">
          <td class="rank" :class="{ 'rank--top': i < 3 }">{{ i + 1 }}</td>
          <td class="name">{{ p.product_name }}</td>
          <td class="cat muted">{{ p.product_category }}</td>
          <td class="num">{{ p.qty }}</td>
          <td class="num strong">¥{{ p.revenue.toLocaleString() }}</td>
          <td class="bar-col">
            <div class="bar">
              <div class="bar__fill" :style="{ width: pct(p.revenue) + '%' }"></div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const max = computed(() => (props.data.length ? props.data[0].revenue : 1))
const pct = (v) => Math.round((v / max.value) * 100)
</script>

<style scoped>
.top__title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}
.top__empty {
  padding: 24px 0;
  text-align: center;
}
.top__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.top__table th {
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-2);
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.top__table td {
  padding: 10px;
  border-bottom: 1px solid #f3f4f6;
}
.top__table tr:last-child td {
  border-bottom: none;
}
.rank {
  width: 34px;
  text-align: center;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
.rank--top {
  color: var(--brand);
  font-weight: 700;
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
.cat {
  font-size: 12px;
}
.bar-col {
  width: 160px;
}
.bar {
  height: 6px;
  background: #f3f4f6;
  border-radius: 3px;
  overflow: hidden;
}
.bar__fill {
  height: 100%;
  background: var(--brand);
  border-radius: 3px;
  transition: width 0.4s ease;
}
</style>