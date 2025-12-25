import { ref, computed, reactive } from 'vue'
import type { Slot } from '~/types/uploads'
import type { Field } from '~/types/metadata'

export function useUploadSlots(metadataSchema: Ref<Field[]>) {
    const slots = ref<Slot[]>([])

    function newSlot(): Slot {
        const values: Record<string, any> = {}
        metadataSchema.value.forEach((f) => {
            values[f.key] = f.default ?? ''
        })
        return reactive<Slot>({
            file: null,
            values,
            error: '',
            working: false,
            progress: 0,
            status: '',
            errors: [],
            paused: false,
            initiated: false,
        })
    }

    function seedSlots(tokenInfo: any) {
        slots.value = []
        if (!tokenInfo) return
        if (!tokenInfo.remaining_uploads || tokenInfo.remaining_uploads <= 0) {
            return
        }
        const count = Math.min(tokenInfo.remaining_uploads, 1)
        for (let i = 0; i < count; i++) slots.value.push(newSlot())
    }

    function addSlot() {
        slots.value.push(newSlot())
    }

    const unintiatedSlots = computed(() => slots.value.filter((s) => !s.initiated))

    return { slots, newSlot, seedSlots, addSlot, unintiatedSlots, }
}
