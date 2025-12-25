import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMetadata } from '~/composables/useMetadata'
import type { Field } from '~/types/metadata'

afterEach(() => {
  vi.restoreAllMocks()
    ; (vi as any).unstubAllGlobals?.()
})

describe('useMetadata', () => {
  const sampleFields: Field[] = [{ key: 'title', label: 'Title', type: 'string' }]

  it('fetches and stores metadata schema', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ fields: sampleFields })
    vi.stubGlobal('$fetch', fetchMock)
    const { metadataSchema, isLoading, fetchMetadata } = useMetadata()

    const fetchPromise = fetchMetadata()
    expect(isLoading.value).toBe(true)

    await fetchPromise

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(isLoading.value).toBe(false)
    expect(metadataSchema.value).toEqual(sampleFields)
  })

  it('skips fetching when schema is already loaded unless forced', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ fields: sampleFields })
    vi.stubGlobal('$fetch', fetchMock)
    const { fetchMetadata } = useMetadata()

    await fetchMetadata()
    await fetchMetadata()
    await fetchMetadata(true)

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('handles fetch errors by clearing schema', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network'))
    vi.stubGlobal('$fetch', fetchMock)
    const { metadataSchema, fetchMetadata } = useMetadata()

    await fetchMetadata()

    expect(metadataSchema.value).toEqual([])
  })
})
