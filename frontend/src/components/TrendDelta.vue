<script setup>
import { computed } from 'vue'

const props = defineProps({
  delta: { type: Number, default: null },
})

const hasData = computed(() => props.delta !== null && props.delta !== undefined)
const rising = computed(() => hasData.value && props.delta >= 0)

const label = computed(() => {
  if (!hasData.value) return 'no data'
  const sign = props.delta >= 0 ? '+' : '−'
  return `${sign}${Math.abs(props.delta).toFixed(1)}%`
})
</script>

<template>
  <span v-if="hasData" class="delta" :class="rising ? 'up' : 'down'">
    <span aria-hidden="true">{{ rising ? '▲' : '▼' }}</span>
    {{ label }}
  </span>
  <span v-else class="muted no-data" title="Google Trends returned no data">—</span>
</template>

<style scoped>
.delta {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.delta.up {
  color: var(--success);
}

.delta.down {
  color: var(--danger);
}

.no-data {
  font-size: 13px;
}
</style>
