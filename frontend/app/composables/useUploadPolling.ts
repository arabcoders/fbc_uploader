import { ref } from 'vue'
import type { Slot } from '~/types/uploads'
import type { TokenInfo } from '~/types/token'

export function useUploadPolling() {
  const pollingIntervals = ref<Map<string, NodeJS.Timeout>>(new Map())

  async function pollUploadStatus(uploadId: string, token: string, slot: Slot, onComplete?: () => void) {
    if (pollingIntervals.value.has(uploadId)) {
      return
    }

    const interval = setInterval(async () => {
      try {
        const { $apiFetch } = useNuxtApp()
        const data = await $apiFetch<TokenInfo>(`/api/tokens/${token}`)
        const upload = data.uploads?.find((u) => u.public_id === uploadId)
        
        if (!upload) {
          stopPolling(uploadId)
          return
        }

        if (upload.status === 'completed') {
          slot.status = 'completed'
          stopPolling(uploadId)
          if (onComplete) {
            onComplete()
          }
        } else if (upload.status === 'failed') {
          slot.status = 'error'
          const errorMsg = upload.meta_data?.error
          slot.error = typeof errorMsg === 'string' ? errorMsg : 'Processing failed'
          stopPolling(uploadId)
        }
      } catch (err) {
        console.error('Failed to poll upload status:', err)
      }
    }, 2000)

    pollingIntervals.value.set(uploadId, interval)
  }

  function stopPolling(uploadId: string) {
    const interval = pollingIntervals.value.get(uploadId)
    if (interval) {
      clearInterval(interval)
      pollingIntervals.value.delete(uploadId)
    }
  }

  function stopAllPolling() {
    pollingIntervals.value.forEach((interval) => clearInterval(interval))
    pollingIntervals.value.clear()
  }

  return {
    pollUploadStatus,
    stopPolling,
    stopAllPolling,
  }
}
