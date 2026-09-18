<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref('')
const taken = ref(false)
const busy = ref(false)

const passwordTooShort = computed(() => password.value.length > 0 && password.value.length < 8)

async function submit() {
  error.value = ''
  taken.value = false
  busy.value = true
  try {
    await auth.register(username.value, password.value)
    await router.push({ name: 'dashboard' })
  } catch (exception) {
    taken.value = exception instanceof ApiError && exception.status === 409
    error.value = taken.value ? '' : exception.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="register">
    <div class="card">
      <h1>Create an account</h1>
      <p class="muted subtitle">Look around the dashboard and start a scrape yourself.</p>

      <p v-if="taken" class="alert error">
        This username is taken.
        <RouterLink :to="{ name: 'login' }">Sign in instead?</RouterLink>
      </p>
      <p v-if="error" class="alert error">{{ error }}</p>

      <form @submit.prevent="submit">
        <div class="field">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            autocomplete="username"
            minlength="3"
            maxlength="32"
            pattern="[A-Za-z0-9_.\-]+"
            title="Letters, digits, dot, dash and underscore"
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
            autocomplete="new-password"
            minlength="8"
            required
          />
          <p v-if="passwordTooShort" class="muted field-hint">At least 8 characters.</p>
        </div>

        <button type="submit" :disabled="busy" class="submit">
          {{ busy ? 'Creating…' : 'Create account' }}
        </button>
      </form>

      <p class="muted hint">
        Already registered? <RouterLink :to="{ name: 'login' }">Sign in</RouterLink>
      </p>
      <p class="muted hint back"><RouterLink :to="{ name: 'home' }">← About Trend Radar</RouterLink></p>
    </div>
  </div>
</template>

<style scoped>
.register {
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

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
}

.hint {
  margin: 18px 0 0;
  font-size: 13px;
  text-align: center;
}

.back {
  margin-top: 8px;
}
</style>
