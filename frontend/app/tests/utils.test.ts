import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText, formatBytes, formatKey, formatValue, percent } from '~/utils'

const originalNavigator = global.navigator

afterEach(() => {
  ; (globalThis as any).navigator = originalNavigator
  vi.restoreAllMocks()
})

describe('copyText', () => {
  it('uses navigator.clipboard when available', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    copyText('hello')

    expect(writeText).toHaveBeenCalledWith('hello')
  })

  it('falls back to execCommand when clipboard API is missing', () => {
    vi.stubGlobal('navigator', {})
    const execSpy = vi.fn()
      ; (document as any).execCommand = execSpy
    const initialTextareas = document.querySelectorAll('textarea').length

    copyText('fallback')

    expect(execSpy).toHaveBeenCalledWith('copy')
    expect(document.querySelectorAll('textarea').length).toBe(initialTextareas)
  })
})

describe('format helpers', () => {
  it('formats bytes to readable units', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(0)).toBe('')
  })

  it('calculates percent safely', () => {
    expect(percent(undefined, undefined)).toBe('—')
    expect(percent(25, 100)).toBe('25%')
    expect(percent(120, 100)).toBe('100%')
  })

  it('formats keys and values for display', () => {
    expect(formatKey('broadcast_date')).toBe('broadcast date')
    expect(formatValue(null)).toBe('—')
    expect(formatValue(['a', 'b'])).toBe('a, b')
    expect(formatValue({ foo: 1 })).toBe(JSON.stringify({ foo: 1 }))
  })
})
