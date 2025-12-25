import { describe, expect, it } from 'vitest'
import { useMetadataParser } from '~/composables/useMetadataParser'
import type { Slot } from '~/types/uploads'
import type { Field } from '~/types/metadata'

function makeSlot(): Slot {
  return {
    file: null,
    values: {},
    error: '',
    working: false,
    progress: 0,
    status: '',
    errors: [],
    paused: false,
    initiated: false,
  }
}

describe('useMetadataParser', () => {
  it('applies extracted metadata values', () => {
    const { applyParsedMeta } = useMetadataParser()
    const slot = makeSlot()
    const schema: Field[] = [{ key: 'source', label: 'Source', type: 'string', extract_regex: 'source-(\\w+)' }]

    applyParsedMeta(slot, 'source-news.mp4', schema)

    expect(slot.values.source).toBe('news')
  })

  it('normalizes parsed dates with named groups', () => {
    const { applyParsedMeta } = useMetadataParser()
    const slot = makeSlot()
    const schema: Field[] = [{
      key: 'broadcast',
      label: 'Broadcast',
      type: 'date',
      extract_regex: '(?<year>\\d{2})(?<month>\\d{2})(?<day>\\d{2})',
    }]

    applyParsedMeta(slot, 'clip_241231_show.mp4', schema)

    expect(slot.values.broadcast).toBe('2024-12-31')
  })
})
