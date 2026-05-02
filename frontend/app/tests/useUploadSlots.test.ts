import { describe, expect, it } from 'bun:test';
import { ref } from 'vue';
import { useUploadSlots } from '~/composables/useUploadSlots';
import type { Field } from '~/types/metadata';

const schema = ref<Field[]>([
  { key: 'title', label: 'Title', type: 'string', default: 'Untitled' },
  { key: 'date', label: 'Date', type: 'date' },
]);

describe('useUploadSlots', () => {
  it('creates slots with default metadata values', () => {
    const { newSlot } = useUploadSlots(schema);
    const slot = newSlot();

    expect(slot.values.title).toBe('Untitled');
    expect(slot.values.date).toBe('');
    expect(slot.initiated).toBe(false);
  });

  it('seeds slots based on remaining uploads', () => {
    const { seedSlots, slots, unintiatedSlots } = useUploadSlots(schema);

    seedSlots({ remaining_uploads: 3 });

    expect(slots.value).toHaveLength(1);
    expect(unintiatedSlots.value).toHaveLength(1);
  });

  it('adds new upload slots on demand', () => {
    const { addSlot, slots } = useUploadSlots(schema);

    addSlot();
    addSlot();

    expect(slots.value).toHaveLength(2);
  });

  it('preserves active initiated slots when reseeding after refresh', () => {
    const { seedSlots, slots } = useUploadSlots(schema);

    seedSlots({ remaining_uploads: 2 });

    const activeSlot = slots.value[0]!;
    activeSlot.initiated = true;
    activeSlot.uploadId = 'upload-1';
    activeSlot.status = 'uploading';
    activeSlot.progress = 50;
    activeSlot.bytesUploaded = 500;

    seedSlots({ remaining_uploads: 1 });

    const refreshedActiveSlot = slots.value[0]!;
    expect(slots.value).toHaveLength(2);
    expect(refreshedActiveSlot).toBe(activeSlot);
    expect(refreshedActiveSlot.progress).toBe(50);
    expect(refreshedActiveSlot.bytesUploaded).toBe(500);
    expect(slots.value[1]?.initiated).toBe(false);
  });

  it('removes completed initiated slots and restores a fresh draft slot', () => {
    const { seedSlots, slots } = useUploadSlots(schema);

    seedSlots({ remaining_uploads: 1 });

    const completedSlot = slots.value[0]!;
    completedSlot.initiated = true;
    completedSlot.status = 'completed';
    completedSlot.uploadId = 'upload-1';

    seedSlots({ remaining_uploads: 1 });

    const refreshedDraftSlot = slots.value[0]!;
    expect(slots.value).toHaveLength(1);
    expect(refreshedDraftSlot).not.toBe(completedSlot);
    expect(refreshedDraftSlot.initiated).toBe(false);
    expect(refreshedDraftSlot.status).toBe('');
  });
});
