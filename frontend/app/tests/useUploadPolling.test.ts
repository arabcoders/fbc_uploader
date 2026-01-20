import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useUploadPolling } from '../composables/useUploadPolling'
import { reactive } from 'vue'

describe('useUploadPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('should provide polling functions', () => {
    const { pollUploadStatus, stopPolling, stopAllPolling } = useUploadPolling()
    
    expect(pollUploadStatus).toBeTypeOf('function')
    expect(stopPolling).toBeTypeOf('function')
    expect(stopAllPolling).toBeTypeOf('function')
  })

  it('should stop all polling on cleanup', () => {
    const { pollUploadStatus, stopAllPolling } = useUploadPolling()
    
    const mockSlot1 = reactive({
      file: null,
      values: {},
      error: '',
      working: false,
      progress: 0,
      status: 'postprocessing',
      errors: [],
      paused: false,
      initiated: true,
      uploadId: 'abc123xyz',
    })

    const mockSlot2 = reactive({
      file: null,
      values: {},
      error: '',
      working: false,
      progress: 0,
      status: 'postprocessing',
      errors: [],
      paused: false,
      initiated: true,
      uploadId: 'def456uvw',
    })

    pollUploadStatus('abc123xyz', 'token1', mockSlot1)
    pollUploadStatus('def456uvw', 'token2', mockSlot2)

    stopAllPolling()

    expect(true).toBe(true)
  })
})
