import { ref, computed } from 'vue'
import type { TokenInfo } from '~/types/token'

export function useTokenInfo(tokenValue: Ref<string>) {
    const tokenInfo = ref<TokenInfo | null>(null)
    const notFound = ref(false)
    const tokenError = ref<string>('')
    const isExpired = ref(false)
    const isDisabled = ref(false)

    const shareLinkText = computed(() => {
        if (!tokenInfo.value) return ''
        return `${window.location.origin}/f/${tokenInfo.value.download_token}`
    })

    async function fetchTokenInfo() {
        if (!tokenValue.value) {
            notFound.value = true
            return
        }
        tokenError.value = ''
        isExpired.value = false
        isDisabled.value = false
        try {
            const { $apiFetch } = useNuxtApp()
            const data = await $apiFetch('/api/tokens/' + tokenValue.value)
            tokenInfo.value = data as any
            notFound.value = false
            
            // Check token status based on returned data
            if (tokenInfo.value) {
                const now = new Date()
                if (tokenInfo.value.expires_at) {
                    const expiresAt = new Date(tokenInfo.value.expires_at)
                    isExpired.value = expiresAt < now
                }
                isDisabled.value = tokenInfo.value.disabled || false
            }
        } catch (err: any) {
            tokenInfo.value = null
            notFound.value = true
            tokenError.value = err?.data?.detail || err?.message || 'Failed to load token info.'
        }
    }

    return { tokenInfo, notFound, tokenError, isExpired, isDisabled, shareLinkText, fetchTokenInfo }
}

