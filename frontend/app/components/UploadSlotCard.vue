<template>
  <UCard variant="outline">
    <template #header>
      <div class="flex items-center gap-3">
        <span class="fbc-section-icon" aria-hidden="true">
          <UIcon name="i-lucide-file-up" class="size-4" />
        </span>
        <h2 class="font-semibold text-highlighted">Upload #{{ index + 1 }}</h2>
      </div>
    </template>

    <div class="space-y-5">
      <UFormField label="File" name="file" required>
        <UFileUpload
          :model-value="uploadSlot.file"
          :accept="acceptAttr"
          :file-image="false"
          :disabled="uploadSlot.working"
          icon="i-lucide-cloud-upload"
          label="Choose a file"
          description="Or drag a file here"
          size="sm"
          layout="list"
          class="w-full"
          :ui="{ base: uploadSlot.file ? 'hidden' : undefined }"
          @update:model-value="(file) => $emit('file', file ?? null)"
        />
      </UFormField>

      <MetadataFields :schema="metadataSchema" v-model="metadataValues" />

      <div class="space-y-2">
        <div class="flex flex-wrap gap-2">
          <UButton
            v-if="!uploadSlot.working && !uploadSlot.paused"
            :disabled="!uploadSlot.file || uploadSlot.errors.length > 0"
            color="primary"
            icon="i-lucide-upload"
            @click="$emit('start')"
          >
            <span v-if="uploadSlot.status === 'validation_failed'">Fix errors then retry</span>
            <span v-else>Start upload</span>
          </UButton>
          <UButton
            v-if="uploadSlot.working && !uploadSlot.paused"
            color="warning"
            icon="i-lucide-pause"
            @click="$emit('pause')"
          >
            Pause
          </UButton>
          <UButton
            v-if="uploadSlot.paused"
            color="primary"
            icon="i-lucide-play"
            @click="$emit('resume')"
          >
            Resume
          </UButton>
        </div>

        <UAlert
          v-if="uploadSlot.file && uploadSlot.errors.length > 0"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          title="Please fix the following:"
        >
          <template #description>
            <ul class="list-disc pl-4 space-y-1 text-sm">
              <li v-for="(err, i) in uploadSlot.errors" :key="i">{{ err }}</li>
            </ul>
          </template>
        </UAlert>

        <div v-if="uploadSlot.status" class="space-y-1">
          <UProgress
            :model-value="uploadSlot.progress"
            size="sm"
            role="group"
            aria-label="Upload progress"
          />
          <p class="text-xs text-toned">
            Status: {{ formatUploadStatus(uploadSlot.status) }} ({{ uploadSlot.progress }}%)
          </p>
        </div>
        <UAlert
          v-if="uploadSlot.error"
          color="error"
          variant="soft"
          icon="i-lucide-triangle-alert"
          :title="uploadSlot.error"
        />
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Field } from '../types/metadata';
import type { Slot } from '../types/uploads';
import MetadataFields from './MetadataFields.vue';
import { formatUploadStatus } from '~/utils';

const emit = defineEmits<{
  file: [File | null];
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
  set: (value) => emit('meta', value),
});
</script>
