<template>
  <div class="kpi card">
    <div class="kpi__label">{{ label }}</div>
    <div v-if="loading" class="kpi__value">
      <span class="skeleton kpi__skeleton"></span>
    </div>
    <div v-else class="kpi__value" :class="{ 'kpi__value--danger': danger }">
      {{ value }}
    </div>
    <div v-if="sub" class="kpi__sub muted">{{ sub }}</div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  sub: { type: String, default: '' },
  danger: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.kpi {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kpi__label {
  font-size: 13px;
  color: var(--text-2);
}
.kpi__value {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--text);
}
.kpi__value--danger {
  color: var(--danger);
}
.kpi__skeleton {
  display: inline-block;
  width: 120px;
  height: 30px;
}
.kpi__sub {
  font-size: 12px;
}
</style>