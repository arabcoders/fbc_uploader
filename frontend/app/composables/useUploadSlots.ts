import { ref, computed, reactive } from 'vue';
import type { Slot } from '~/types/uploads';
import type { Field } from '~/types/metadata';

export function useUploadSlots(metadataSchema: Ref<Field[]>) {
  const slots = ref<Slot[]>([]);

  function newSlot(): Slot {
    const values: Record<string, any> = {};
    metadataSchema.value.forEach((f) => {
      values[f.key] = f.default ?? '';
    });
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
    });
  }

  function hasDraftContent(slot: Slot): boolean {
    if (slot.file || slot.error || slot.errors.length > 0 || slot.status) {
      return true;
    }

    return Object.values(slot.values).some((value) => {
      if (value === null || value === undefined) return false;
      if (typeof value === 'string') return value.trim().length > 0;
      if (Array.isArray(value)) return value.length > 0;
      return true;
    });
  }

  function seedSlots(tokenInfo: any, reset = false) {
    const preservedSlots = reset
      ? []
      : slots.value.filter((slot) => {
          if (slot.initiated) {
            return slot.status !== 'completed';
          }

          return hasDraftContent(slot);
        });

    slots.value = preservedSlots;

    if (!tokenInfo) return;
    if (!tokenInfo.remaining_uploads || tokenInfo.remaining_uploads <= 0) {
      return;
    }

    const draftSlots = slots.value.filter((slot) => !slot.initiated);
    const count = Math.min(tokenInfo.remaining_uploads, 1);
    const missingSlots = Math.max(0, count - draftSlots.length);

    for (let i = 0; i < missingSlots; i++) {
      slots.value.push(newSlot());
    }
  }

  function addSlot() {
    slots.value.push(newSlot());
  }

  const unintiatedSlots = computed(() => slots.value.filter((s) => !s.initiated));

  return { slots, newSlot, seedSlots, addSlot, unintiatedSlots };
}
