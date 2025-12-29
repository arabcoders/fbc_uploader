import { ref, computed } from 'vue'
import type { TokenInfo } from '~/types/token'

export function useTokenInfo(tokenValue: Ref<string>) {
    const tokenInfo = ref<TokenInfo | null>(null)
    const notFound = ref(false)
    const tokenError = ref<string>('')

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
        try {
            const data = await $fetch('/api/tokens/' + tokenValue.value + '/info')
            tokenInfo.value = data as any
            notFound.value = false
        } catch (err: any) {
            tokenInfo.value = null
            notFound.value = true
            tokenError.value = err?.data?.detail || err?.message || 'Failed to load token info.'
        }
    }

    return { tokenInfo, notFound, tokenError, shareLinkText, fetchTokenInfo }
}
