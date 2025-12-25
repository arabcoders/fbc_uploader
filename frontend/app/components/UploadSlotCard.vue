<template>
  <UCard>
    <template #header>
      <div class="flex items-center gap-2">
        <UIcon name="i-heroicons-document-arrow-up-20-solid" />
        <span class="font-semibold">Upload #{{ index + 1 }}</span>
      </div>
    </template>

    <div class="space-y-4">
      <div class="space-y-2">
        <label class="text-sm font-medium">File</label>
        <UInput type="file" class="w-full" :accept="acceptAttr" @change="(e: Event) => $emit('file', e)" />
      </div>

      <MetadataFields :schema="metadataSchema" v-model="metadataValues" />

      <div class="space-y-2">
        <div class="flex gap-2">
          <UButton v-if="!uploadSlot.working && !uploadSlot.paused"
            :disabled="!uploadSlot.file || uploadSlot.errors.length > 0" color="primary"
            icon="i-heroicons-cloud-arrow-up-20-solid" @click="$emit('start')">
            <span v-if="uploadSlot.status === 'validation_failed'">Fix errors then retry</span>
            <span v-else>Start upload</span>
          </UButton>
          <UButton v-if="uploadSlot.working && !uploadSlot.paused" color="warning" icon="i-heroicons-pause-20-solid"
            @click="$emit('pause')">
            Pause
          </UButton>
          <UButton v-if="uploadSlot.paused" color="primary" icon="i-heroicons-play-20-solid" @click="$emit('resume')">
            Resume
          </UButton>
        </div>

        <UAlert v-if="uploadSlot.file && uploadSlot.errors.length > 0" color="error" variant="subtle"
          icon="i-heroicons-exclamation-circle-20-solid" title="Please fix these:">
          <template #description>
            <ul class="list-disc pl-4 space-y-1 text-sm">
              <li v-for="(err, i) in uploadSlot.errors" :key="i">{{ err }}</li>
            </ul>
          </template>
        </UAlert>

        <div v-if="uploadSlot.status" class="space-y-1">
          <UProgress :value="uploadSlot.progress" size="sm" color="primary" />
          <p class="text-xs opacity-70">Status: {{ uploadSlot.status }} ({{ uploadSlot.progress }}%)</p>
        </div>
        <UAlert v-if="uploadSlot.error" color="error" variant="soft" icon="i-heroicons-exclamation-triangle-20-solid"
          :title="uploadSlot.error" />
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Field } from "../types/metadata";
import type { Slot } from "../types/uploads";
import MetadataFields from "./MetadataFields.vue";

const emit = defineEmits<{
  file: [Event];
  start: [];
  pause: [];
  resume: [];
  meta: [Record<string, any>];
}>();

const props = defineProps<{
  index: number;
  uploadSlot: Slot;
  metadataSchema: Field[];
  acceptAttr?: string;
}>();

const metadataValues = computed({
  get: () => props.uploadSlot.values,
  set: (value) => emit('meta', value)
});
</script>
