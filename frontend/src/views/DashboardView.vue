<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import RunStatus from '@/components/RunStatus.vue'
import ScoreCell from '@/components/ScoreCell.vue'
import TrendDelta from '@/components/TrendDelta.vue'
import { useApiError } from '@/composables/useApiError'

const toMessage = useApiError()

const PAGE_SIZE = 50
const POLL_MS = 3000

const products = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const starting = ref(false)
const error = ref('')
const run = ref(null)
const expanded = ref(new Set())
// Amazon image URLs rot, so a failed load falls back to a placeholder.
const brokenImages = ref(new Set())

let timer = null

const isRunActive = computed(() => ['pending', 'running'].includes(run.value?.status))
const canGoBack = computed(() => offset.value > 0)
const canGoForward = computed(() => offset.value + PAGE_SIZE < total.value)

const shown = computed(() => {
  if (!total.value) return '0'
  return `${offset.value + 1}–${offset.value + products.value.length} of ${total.value}`
})

async function loadProducts() {
  loading.value = true
  try {
    const response = await api.listProducts({ limit: PAGE_SIZE, offset: offset.value })
    products.value = response.items
    total.value = response.total
  } catch (exception) {
    error.value = toMessage(exception)
  } finally {
    loading.value = false
  }
}

async function refreshRun() {
  try {
    const previous = run.value?.status
    run.value = await api.latestRun()

    if (['pending', 'running'].includes(previous) && !isRunActive.value) {
      await loadProducts()
    }
    schedulePoll()
  } catch (exception) {
    error.value = toMessage(exception)
  }
}

function schedulePoll() {
  clearTimeout(timer)
  if (isRunActive.value) {
    timer = setTimeout(refreshRun, POLL_MS)
  }
}

async function startRun() {
  error.value = ''
  starting.value = true
  try {
    run.value = await api.startRun()
    schedulePoll()
  } catch (exception) {
    error.value = toMessage(exception)
  } finally {
    starting.value = false
  }
}

async function changePage(delta) {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  await loadProducts()
}

function toggleReasoning(id) {
  // Reassigned, not mutated: Vue does not track Set membership.
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}

function markImageBroken(id) {
  brokenImages.value = new Set(brokenImages.value).add(id)
}

function formatPrice(product) {
  if (product.price === null || product.price === undefined) return '—'
  return `${Number(product.price).toFixed(2)} ${product.currency}`
}

function formatRating(product) {
  return product.rating === null || product.rating === undefined
    ? '—'
    : product.rating.toFixed(1)
}

onMounted(async () => {
  await Promise.all([loadProducts(), refreshRun()])
})

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <section>
    <header class="head">
      <div>
        <h1>Dashboard</h1>
        <p class="muted subtitle">
          Amazon best sellers scored from trend dynamics, our sales history and the LLM.
        </p>
      </div>

      <button type="button" :disabled="starting || isRunActive" @click="startRun">
        {{ isRunActive ? 'Collecting…' : 'Run trend collection' }}
      </button>
    </header>

    <p v-if="error" class="alert error">{{ error }}</p>

    <div v-if="run" class="card run-card">
      <RunStatus :run="run" />
    </div>

    <div class="card">
      <div class="toolbar">
        <h2>Products</h2>
        <span class="muted count">{{ shown }}</span>
      </div>

      <p v-if="loading" class="muted state">Loading…</p>

      <p v-else-if="!products.length" class="muted state">
        No products yet. Press “Run trend collection” — the first run takes a few minutes.
      </p>

      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Photo</th>
              <th>Title</th>
              <th>Category</th>
              <th>Price</th>
              <th>Rating</th>
              <th>Reviews</th>
              <th>Trend</th>
              <th>Score</th>
              <th>Reasoning</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="product in products" :key="product.id">
              <td>
                <img
                  v-if="product.image_url && !brokenImages.has(product.id)"
                  :src="product.image_url"
                  :alt="product.title"
                  class="thumb"
                  loading="lazy"
                  @error="markImageBroken(product.id)"
                />
                <span v-else class="thumb placeholder" title="No photo available">🛒</span>
              </td>

              <td class="title-cell">
                <a :href="product.product_url" target="_blank" rel="noopener noreferrer">
                  {{ product.title }}
                </a>
                <span class="muted asin">{{ product.asin }}</span>
              </td>

              <td>{{ product.category }}</td>
              <td class="num">{{ formatPrice(product) }}</td>
              <td class="num">{{ formatRating(product) }}</td>
              <td class="num">{{ product.reviews_count.toLocaleString() }}</td>
              <td><TrendDelta :delta="product.trend_delta_pct" /></td>

              <td>
                <ScoreCell :score="product.score" />
                <div v-if="product.score" class="score-meta muted">
                  <span :title="'Sales Boost points included in the score'">
                    boost +{{ product.score.boost_score }}
                  </span>
                  <span class="provider">{{ product.score.provider }}</span>
                </div>
              </td>

              <td class="reasoning-cell">
                <template v-if="product.score">
                  <p :class="['reasoning', { clamped: !expanded.has(product.id) }]">
                    {{ product.score.reasoning }}
                  </p>
                  <button
                    type="button"
                    class="link"
                    @click="toggleReasoning(product.id)"
                  >
                    {{ expanded.has(product.id) ? 'Show less' : 'Show more' }}
                  </button>
                </template>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="canGoBack || canGoForward" class="pager">
        <button
          type="button"
          class="secondary"
          :disabled="!canGoBack || loading"
          @click="changePage(-1)"
        >
          Previous
        </button>
        <button
          type="button"
          class="secondary"
          :disabled="!canGoForward || loading"
          @click="changePage(1)"
        >
          Next
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--gap);
  flex-wrap: wrap;
  margin-bottom: var(--gap);
}

.subtitle {
  margin: 6px 0 0;
  font-size: 14px;
  max-width: 62ch;
}

.run-card {
  margin-bottom: var(--gap);
  padding: 14px 20px;
}

.toolbar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gap);
  margin-bottom: 14px;
}

.toolbar h2 {
  font-size: 16px;
}

.count {
  font-size: 13px;
}

.state {
  margin: 6px 0;
  font-size: 14px;
}

.thumb {
  width: 52px;
  height: 52px;
  object-fit: contain;
  background: var(--surface-raised);
  border-radius: var(--radius-sm);
}

.thumb.placeholder {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  opacity: 0.45;
}

.title-cell {
  min-width: 240px;
  max-width: 320px;
}

.asin {
  display: block;
  font-size: 11px;
  margin-top: 2px;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.score-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  margin-top: 5px;
}

.provider {
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.reasoning-cell {
  min-width: 260px;
  max-width: 380px;
}

.reasoning {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  white-space: pre-line;
}

.reasoning.clamped {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.link {
  background: none;
  color: var(--accent);
  padding: 2px 0;
  font-size: 12px;
}

.link:hover:not(:disabled) {
  background: none;
  text-decoration: underline;
}

.pager {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: var(--gap);
}

@media (max-width: 640px) {
  .head button {
    width: 100%;
  }
}
</style>
