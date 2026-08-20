<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const showChrome = computed(() => route.name !== 'login')

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <header v-if="showChrome" class="topbar">
      <div class="brand">
        <span class="dot" aria-hidden="true"></span>
        <span>Trend Radar</span>
      </div>

      <nav>
        <RouterLink :to="{ name: 'dashboard' }">Dashboard</RouterLink>
        <RouterLink :to="{ name: 'sales-boost' }">Sales Boost</RouterLink>
      </nav>

      <div class="account">
        <span class="muted">{{ auth.user?.username }}</span>
        <button class="secondary" type="button" @click="logout">Log out</button>
      </div>
    </header>

    <main :class="{ centered: !showChrome }">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 14px 28px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 600;
  font-size: 16px;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
}

nav {
  display: flex;
  gap: 6px;
}

nav a {
  padding: 7px 13px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
}

nav a:hover {
  color: var(--text);
  text-decoration: none;
  background: var(--surface-raised);
}

nav a.router-link-active {
  color: var(--text);
  background: var(--surface-raised);
}

.account {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 14px;
}

main {
  flex: 1;
  padding: 26px 28px 44px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

main.centered {
  display: grid;
  place-items: center;
  padding: 20px;
}

@media (max-width: 640px) {
  .topbar {
    padding: 12px 16px;
    gap: 14px;
  }

  main {
    padding: 18px 16px 32px;
  }
}
</style>
