import { describe, expect, it } from 'vitest'
import { validateSlot } from '~/utils/validation'
import type { Slot } from '~/types/uploads'
import type { Field } from '~/types/metadata'

function buildSlot(overrides: Partial<Slot> = {}): Slot {
  return {
    file: { name: 'test.mp4', size: 1_000, type: 'video/mp4' } as any,
    values: {},
    error: '',
    working: false,
    progress: 0,
    status: '',
    errors: [],
    paused: false,
    initiated: false,
    ...overrides,
  }
}

describe('validateSlot', () => {
  it('flags missing required fields', () => {
    const schema: Field[] = [{ key: 'title', label: 'Title', type: 'string', required: true }]
    const slot = buildSlot()

    const errors = validateSlot(slot, schema, null)

    expect(errors).toContain('Title is required')
    expect(slot.errors).toEqual(errors)
  })

  it('validates numeric bounds', () => {
    const schema: Field[] = [{ key: 'score', label: 'Score', type: 'number', min: 10, max: 20 }]
    const slot = buildSlot({ values: { score: 'abc' } })

    let errors = validateSlot(slot, schema, null)
    expect(errors).toContain('Score must be numeric')

    slot.values.score = 5
    errors = validateSlot(slot, schema, null)
    expect(errors).toContain('Score must be >= 10')

    slot.values.score = 25
    errors = validateSlot(slot, schema, null)
    expect(errors).toContain('Score must be <= 20')
  })

  it('rejects invalid select options', () => {
    const schema: Field[] = [{ key: 'color', label: 'Color', type: 'select', options: ['red', 'blue'] }]
    const slot = buildSlot({ values: { color: 'green' } })

    const errors = validateSlot(slot, schema, null)

    expect(errors).toContain('Color has invalid option')
  })

  it('splits multiselect custom values', () => {
    const schema: Field[] = [{ key: 'tags', label: 'Tags', type: 'multiselect', allowCustom: true }]
    const slot = buildSlot({ values: { tags: 'news,  sports ,  ' } })

    const errors = validateSlot(slot, schema, null)

    expect(errors).toHaveLength(0)
    expect(slot.values.tags).toEqual(['news', 'sports'])
  })

  it('checks file size against token limits', () => {
    const schema: Field[] = [{ key: 'title', label: 'Title', type: 'string', required: false }]
    const slot = buildSlot({ file: { name: 'big.mp4', size: 2_000_000, type: 'video/mp4' } as any })

    const errors = validateSlot(slot, schema, { max_size_bytes: 1_000_000 } as any)

    expect(errors.some((e) => e.includes('exceeds max size'))).toBe(true)
  })
})
