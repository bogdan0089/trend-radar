<script setup>
import { computed } from 'vue'

const props = defineProps({
  run: { type: Object, default: null },
})

const TONES = {
  success: 'success',
  partial: 'warning',
  failed: 'danger',
  running: '',
  pending: '',
}

const tone = computed(() => TONES[props.run?.status] ?? '')

const summary = computed(() => {
  const run = props.run
  if (!run) return ''
  if (run.status === 'pending') return 'queued, waiting for a worker'
  if (run.status === 'running') return 'collecting…'

  return `${run.products_found} products · ${run.trends_collected} trends · ${run.scores_created} scores`
})

const finishedAt = computed(() => {
  const value = props.run?.finished_at
  return value ? new Date(value).toLocaleString() : null
})
</script>

<template>
  <div v-if="run" class="run">
    <span class="badge" :class="tone">{{ run.status }}</span>
    <span class="muted">{{ summary }}</span>
    <span v-if="finishedAt" class="muted time">· {{ finishedAt }}</span>

    <!-- 'partial' carries the reason: a block or a category that failed. It has
         to stay visible, otherwise a dead scraper looks like a normal run. -->
    <p v-if="run.error" class="reason muted">{{ run.error }}</p>
  </div>
</template>

<style scoped>
.run {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  font-size: 13px;
}

.time {
  font-size: 12px;
}

.reason {
  flex-basis: 100%;
  margin: 2px 0 0;
  font-size: 12px;
}
</style>
