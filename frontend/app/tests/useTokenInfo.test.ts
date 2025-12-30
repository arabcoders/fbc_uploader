import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useTokenInfo } from '~/composables/useTokenInfo'

afterEach(() => {
  vi.restoreAllMocks()
    ; (vi as any).unstubAllGlobals?.()
})

describe('useTokenInfo', () => {
  it('populates token info and share link on success', async () => {
    const tokenValue = ref('abc123')
    const fetchMock = vi.fn().mockResolvedValue({
      download_token: 'dl-token',
      remaining_uploads: 2,
      max_uploads: 5,
      expires_at: '2024-12-01T00:00:00Z',
    })
    vi.stubGlobal('$fetch', fetchMock)

    const { tokenInfo, notFound, shareLinkText, fetchTokenInfo } = useTokenInfo(tokenValue)

    await fetchTokenInfo()

    expect(fetchMock).toHaveBeenCalledWith('/api/tokens/abc123')
    expect(notFound.value).toBe(false)
    expect(tokenInfo.value?.download_token).toBe('dl-token')
    expect(shareLinkText.value).toBe(`${window.location.origin}/f/dl-token`)
  })

  it('sets error state when fetch fails', async () => {
    const tokenValue = ref('missing')
    const fetchMock = vi.fn().mockRejectedValue({ data: { detail: 'No token' } })
    vi.stubGlobal('$fetch', fetchMock)

    const { tokenInfo, notFound, tokenError, fetchTokenInfo } = useTokenInfo(tokenValue)

    await fetchTokenInfo()

    expect(tokenInfo.value).toBeNull()
    expect(notFound.value).toBe(true)
    expect(tokenError.value).toBe('No token')
  })
})
