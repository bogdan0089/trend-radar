<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Object, default: null },
})

const tone = computed(() => {
  if (!props.score) return ''
  if (props.score.score >= 70) return 'high'
  if (props.score.score >= 45) return 'mid'
  return 'low'
})
</script>

<template>
  <div v-if="score" class="score" :class="tone">
    <span class="value">{{ score.score }}</span>
    <span class="max">/100</span>
  </div>
  <span v-else class="muted pending">not scored yet</span>
</template>

<style scoped>
.score {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-raised);
}

.value {
  font-size: 18px;
  font-weight: 700;
}

.max {
  font-size: 11px;
  color: var(--text-muted);
}

.score.high {
  color: var(--success);
  border-color: rgba(53, 194, 122, 0.45);
}

.score.mid {
  color: var(--warning);
  border-color: rgba(224, 166, 53, 0.45);
}

.score.low {
  color: var(--danger);
  border-color: rgba(229, 84, 75, 0.45);
}

.pending {
  font-size: 13px;
  font-style: italic;
}
</style>
