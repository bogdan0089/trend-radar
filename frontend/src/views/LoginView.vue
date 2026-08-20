<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(username.value, password.value)
    await router.push(route.query.redirect || { name: 'dashboard' })
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="card">
      <h1>Trend Radar</h1>
      <p class="muted subtitle">Sign in to open the dashboard.</p>

      <p v-if="error" class="alert error">{{ error }}</p>

      <form @submit.prevent="submit">
        <div class="field">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            autocomplete="username"
            required
            autofocus
          />
        </div>

        <div class="field">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>

        <button type="submit" :disabled="busy" class="submit">
          {{ busy ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

      <p class="muted hint">Demo account: <code>admin</code> / <code>admin123</code></p>
    </div>
  </div>
</template>

<style scoped>
.login {
  width: 100%;
  max-width: 380px;
}

.subtitle {
  margin: 6px 0 20px;
  font-size: 14px;
}

.submit {
  width: 100%;
  margin-top: 4px;
}

.hint {
  margin: 18px 0 0;
  font-size: 13px;
  text-align: center;
}

code {
  background: var(--surface-raised);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
