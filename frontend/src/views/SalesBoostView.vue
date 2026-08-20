<script setup>
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import { useApiError } from '@/composables/useApiError'

const toMessage = useApiError()

const PAGE_SIZE = 100

const items = ref([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const notice = ref('')

const form = ref({ title: '', category: '', keywords: '', notes: '' })
const saving = ref(false)

const fileInput = ref(null)
const selectedFile = ref(null)
const importing = ref(false)
const report = ref(null)

const canSubmit = computed(
  () => form.value.title.trim() !== '' && form.value.category.trim() !== '',
)

async function load() {
  loading.value = true
  try {
    const response = await api.listPastProducts({ limit: PAGE_SIZE })
    items.value = response.items
    total.value = response.total
  } catch (exception) {
    error.value = toMessage(exception)
  } finally {
    loading.value = false
  }
}

function splitKeywords(value) {
  return value
    .replace(/;/g, ',')
    .split(',')
    .map((word) => word.trim())
    .filter(Boolean)
}

async function submitForm() {
  error.value = ''
  notice.value = ''
  saving.value = true

  try {
    const created = await api.createPastProduct({
      title: form.value.title.trim(),
      category: form.value.category.trim(),
      keywords: splitKeywords(form.value.keywords),
      notes: form.value.notes.trim() || null,
    })
    form.value = { title: '', category: '', keywords: '', notes: '' }
    notice.value = `Added “${created.title}”.`
    await load()
  } catch (exception) {
    error.value = toMessage(exception)
  } finally {
    saving.value = false
  }
}

function pickFile(event) {
  selectedFile.value = event.target.files?.[0] ?? null
  report.value = null
}

async function importCsv() {
  if (!selectedFile.value) return

  error.value = ''
  notice.value = ''
  report.value = null
  importing.value = true

  try {
    report.value = await api.importPastProductsCsv(selectedFile.value)
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await load()
  } catch (exception) {
    error.value = toMessage(exception)
  } finally {
    importing.value = false
  }
}

function formatDate(value) {
  return new Date(value).toLocaleDateString()
}

onMounted(load)
</script>

<template>
  <section>
    <header class="head">
      <div>
        <h1>Sales Boost</h1>
        <p class="muted subtitle">
          Our past successful products. A scraped product matching one of these by
          category or keywords earns extra points in its score.
        </p>
      </div>
    </header>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="notice" class="alert success">{{ notice }}</p>

    <div class="forms">
      <div class="card">
        <h2>Add manually</h2>

        <form @submit.prevent="submitForm">
          <div class="field">
            <label for="title">Title</label>
            <input id="title" v-model="form.title" maxlength="500" required />
          </div>

          <div class="field">
            <label for="category">Category</label>
            <input id="category" v-model="form.category" maxlength="255" required />
          </div>

          <div class="field">
            <label for="keywords">Keywords (comma separated, optional)</label>
            <input id="keywords" v-model="form.keywords" placeholder="yoga, mat, fitness" />
            <p class="muted hint">Left empty, they are derived from the title.</p>
          </div>

          <div class="field">
            <label for="notes">Notes (optional)</label>
            <textarea id="notes" v-model="form.notes" rows="3" maxlength="2000" />
          </div>

          <button type="submit" :disabled="saving || !canSubmit">
            {{ saving ? 'Saving…' : 'Add product' }}
          </button>
        </form>
      </div>

      <div class="card">
        <h2>Import CSV</h2>

        <p class="muted hint">
          Required columns: <code>title</code>, <code>category</code>. Optional:
          <code>keywords</code>, <code>notes</code>. Up to 5 MB.
        </p>

        <div class="field">
          <label for="csv">CSV file</label>
          <input id="csv" ref="fileInput" type="file" accept=".csv,text/csv" @change="pickFile" />
        </div>

        <button type="button" :disabled="!selectedFile || importing" @click="importCsv">
          {{ importing ? 'Importing…' : 'Import' }}
        </button>

        <div v-if="report" class="report">
          <p>
            Imported <strong>{{ report.imported }}</strong>, skipped
            <strong>{{ report.skipped }}</strong>.
          </p>
          <ul v-if="report.errors.length" class="muted errors">
            <li v-for="(message, index) in report.errors" :key="index">{{ message }}</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card list">
      <div class="toolbar">
        <h2>Past products</h2>
        <span class="muted count">{{ total }} total</span>
      </div>

      <p v-if="loading" class="muted state">Loading…</p>

      <p v-else-if="!items.length" class="muted state">
        Nothing here yet. Add a product with the form or import a CSV.
      </p>

      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Category</th>
              <th>Keywords</th>
              <th>Notes</th>
              <th>Source</th>
              <th>Added</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td class="title-cell">{{ item.title }}</td>
              <td>{{ item.category }}</td>
              <td class="keywords-cell">
                <span v-for="word in item.keywords" :key="word" class="badge tag">{{ word }}</span>
                <span v-if="!item.keywords.length" class="muted">—</span>
              </td>
              <td class="notes-cell">{{ item.notes || '—' }}</td>
              <td><span class="badge">{{ item.source }}</span></td>
              <td class="nowrap">{{ formatDate(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.head {
  margin-bottom: var(--gap);
}

.subtitle {
  margin: 6px 0 0;
  font-size: 14px;
  max-width: 68ch;
}

.forms {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--gap);
  align-items: start;
}

.forms h2,
.toolbar h2 {
  font-size: 16px;
}

.forms h2 {
  margin-bottom: 14px;
}

.hint {
  margin: 6px 0 0;
  font-size: 12px;
}

.report {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 14px;
}

.report p {
  margin: 0;
}

.errors {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
}

.list {
  margin-top: var(--gap);
}

.toolbar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--gap);
  margin-bottom: 14px;
}

.count,
.state {
  font-size: 13px;
}

.state {
  margin: 6px 0;
}

.title-cell {
  min-width: 200px;
  max-width: 320px;
}

.keywords-cell {
  min-width: 180px;
  max-width: 280px;
}

.tag {
  margin: 0 4px 4px 0;
}

.notes-cell {
  max-width: 280px;
  color: var(--text-muted);
  font-size: 13px;
}

.nowrap {
  white-space: nowrap;
}

code {
  background: var(--surface-raised);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}

input[type='file'] {
  padding: 7px 10px;
}
</style>
