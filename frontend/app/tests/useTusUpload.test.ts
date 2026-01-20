import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Slot } from '~/types/uploads'

const makeSlot = (): Slot => ({
  file: null,
  values: {},
  error: '',
  working: false,
  progress: 0,
  status: '',
  errors: [],
  paused: false,
  initiated: false,
  uploadId: 'test-upload-id',
})

// Create a configurable mock Upload class
// eslint-disable-next-line @typescript-eslint/no-extraneous-class
class MockUpload {
  static implementation: any = null

  constructor(file: any, opts: any) {
    if (MockUpload.implementation) {
      return MockUpload.implementation(file, opts)
    }
    return {
      start: () => { },
    }
  }
}

// Mock tus-js-client at the module level
vi.mock('tus-js-client', () => ({
  Upload: MockUpload,
}))

beforeEach(() => {
  MockUpload.implementation = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useTusUpload', () => {
  it('starts upload and marks completion', async () => {
    MockUpload.implementation = (_file: any, opts: any) => ({
      start: () => {
        opts.onProgress(5, 10)
        opts.onSuccess()
      },
    })

    const { useTusUpload } = await import('~/composables/useTusUpload')
    const { startTusUpload } = useTusUpload()
    const slot = makeSlot()
    const file = { name: 'a.bin', size: 10, type: 'application/octet-stream' } as File

    await startTusUpload(slot, 'http://upload', file, { max_chunk_bytes: 50 } as any)

    expect(slot.status).toBe('postprocessing')
    expect(slot.progress).toBe(100)
    expect(slot.tusUpload).toBeUndefined()
  })

  it('pauses and resumes existing upload', () => {
    const abort = vi.fn()
    const start = vi.fn()
    const slot = makeSlot()
    slot.tusUpload = { abort, start } as any
    slot.paused = false
    slot.working = true

    return import('~/composables/useTusUpload').then(({ useTusUpload }) => {
      const { pauseUpload, resumeUpload } = useTusUpload()
      pauseUpload(slot)
      expect(slot.paused).toBe(true)
      expect(slot.status).toBe('paused')
      expect(slot.working).toBe(false)
      expect(abort).toHaveBeenCalled()

      resumeUpload(slot)
      expect(slot.paused).toBe(false)
      expect(slot.status).toBe('uploading')
      expect(slot.working).toBe(true)
      expect(start).toHaveBeenCalled()
    })
  })
})
