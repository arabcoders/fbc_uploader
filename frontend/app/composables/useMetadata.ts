import { ref, nextTick } from 'vue';
import type { Field } from '~/types/metadata';

export function useMetadata() {
  const isLoading = ref(false);
  const metadataSchema = ref<Field[]>([]);

  async function fetchMetadata(force: boolean = false) {
    if (false === force && (isLoading.value || metadataSchema.value.length > 0)) {
      return;
    }
    isLoading.value = true;
    await nextTick();

    try {
      const data = await $fetch<{ fields: Field[] }>('/api/metadata/');
      metadataSchema.value = data.fields || [];
    } catch {
      metadataSchema.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function extractMetadata(filename: string): Promise<Record<string, any>> {
    try {
      const data = await $fetch<{ metadata: Record<string, any> }>('/api/metadata/extract', {
        method: 'POST',
        body: { filename },
      });
      return data.metadata || {};
    } catch {
      return {};
    }
  }

  return { isLoading, metadataSchema, fetchMetadata, extractMetadata };
}
