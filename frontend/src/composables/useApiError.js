import { useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

export function useApiError() {
  const auth = useAuthStore()
  const router = useRouter()

  return function toMessage(exception) {
    if (exception instanceof ApiError && exception.isUnauthorized) {
      auth.logout()
      router.push({ name: 'login' })
      return 'The session has expired. Please sign in again.'
    }
    return exception.message || 'Something went wrong.'
  }
}
