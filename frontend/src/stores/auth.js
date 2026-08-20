import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

import { api, getToken, setToken } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const user = ref(null)
  const isAuthenticated = computed(() => Boolean(token.value))

  async function login(username, password) {
    const response = await api.login(username, password)
    token.value = response.access_token
    setToken(response.access_token)
    user.value = await api.me()
  }

  function logout() {
    token.value = null
    user.value = null
    setToken(null)
  }

  async function restore() {
    if (!token.value) {
      return false
    }
    try {
      user.value = await api.me()
      return true
    } catch {
      logout()
      return false
    }
  }

  return { token, user, isAuthenticated, login, logout, restore }
})
