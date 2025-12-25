import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useUploadSlots } from '~/composables/useUploadSlots'
import type { Field } from '~/types/metadata'

const schema = ref<Field[]>([
  { key: 'title', label: 'Title', type: 'string', default: 'Untitled' },
  { key: 'date', label: 'Date', type: 'date' },
])

describe('useUploadSlots', () => {
  it('creates slots with default metadata values', () => {
    const { newSlot } = useUploadSlots(schema)
    const slot = newSlot()

    expect(slot.values.title).toBe('Untitled')
    expect(slot.values.date).toBe('')
    expect(slot.initiated).toBe(false)
  })

  it('seeds slots based on remaining uploads', () => {
    const { seedSlots, slots, unintiatedSlots } = useUploadSlots(schema)

    seedSlots({ remaining_uploads: 3 })

    expect(slots.value).toHaveLength(1)
    expect(unintiatedSlots.value).toHaveLength(1)
  })

  it('adds new upload slots on demand', () => {
    const { addSlot, slots } = useUploadSlots(schema)

    addSlot()
    addSlot()

    expect(slots.value).toHaveLength(2)
  })
})
