<template>
  <UContainer class="py-6 sm:py-8">
    <div class="space-y-6">
      <PageHeader
        section="File transfer"
        title="Upload files"
        icon="i-lucide-cloud-upload"
        description="Add files using this upload link."
      />

      <div v-if="loading" class="space-y-3" role="status">
        <span class="sr-only">Loading upload link</span>
        <USkeleton class="h-20 w-full" />
        <USkeleton class="h-48 w-full" />
      </div>

      <div v-else-if="notFound && !tokenInfo">
        <UAlert
          color="error"
          variant="soft"
          :title="tokenError || 'Token not found'"
          icon="i-lucide-triangle-alert"
        />
      </div>

      <div v-else-if="tokenInfo && (isExpired || isDisabled)">
        <UAlert
          v-if="isExpired"
          color="warning"
          variant="soft"
          title="Token has expired"
          description="This upload token has expired and can no longer be used."
          icon="i-lucide-clock"
        />
        <UAlert
          v-else-if="isDisabled"
          color="warning"
          variant="soft"
          title="Token is disabled"
          description="This token has been disabled and can no longer be used."
          icon="i-lucide-lock"
        />
      </div>

      <template v-else-if="tokenInfo">
        <UCard variant="outline">
          <TokenSummary
            :token-info="tokenInfo"
            :share-link="shareLinkText"
            :share-path="shareLinkPath"
            :share-disabled="!canShare"
            @copy="copyShareLink"
            @refresh="refreshAll"
          />
        </UCard>

        <UploadNotice v-if="notice" v-model:open="showNotice" :content="notice" />

        <div v-if="allRows.length > 0" class="space-y-3">
          <div class="flex items-center gap-3">
            <span class="fbc-section-icon" aria-hidden="true">
              <UIcon name="i-lucide-list" class="size-4" />
            </span>
            <h2 class="font-semibold text-highlighted">Uploads</h2>
          </div>
          <UploadsTable
            :rows="allRows"
            :allow-downloads="tokenInfo?.allow_public_downloads ?? false"
            @resume="handleResume"
            @pause="handlePause"
            @cancel="handleCancel"
          />
        </div>

        <UEmpty
          v-else-if="!showForms"
          title="No files uploaded"
          description="This token has no remaining upload slots."
          icon="i-lucide-inbox"
        />

        <div v-if="showForms" class="space-y-4">
          <div class="grid items-start gap-4 lg:grid-cols-2">
            <UploadSlotCard
              v-for="(slot, idx) in unintiatedSlots"
              :key="idx"
              :index="idx"
              :upload-slot="slot"
              :metadata-schema="metadataSchema"
              :accept-attr="acceptAttr"
              @file="(file) => onFile(slot, file)"
              @meta="(v) => onMetaChange(slot, v)"
              @start="start(slot, idx)"
            />
          </div>
          <UButton
            v-if="canAddMoreSlots"
            color="neutral"
            variant="outline"
            icon="i-lucide-plus"
            @click="addSlot"
          >
            Add another upload ({{ (tokenInfo?.remaining_uploads || 0) - unintiatedSlots.length }}
            remaining)
          </UButton>
        </div>
      </template>
    </div>
    <input ref="resumeInput" type="file" class="hidden" @change="onResumeFile" />
  </UContainer>
</template>

<script setup lang="ts">
import { formatBytes } from '~/utils';
import { computed, ref, watch, onMounted, onUnmounted, reactive } from 'vue';
import { useRoute } from 'vue-router';
import type {
  UploadRow,
  Slot,
  UploadRowWithSlot,
  InitiateUploadResponse,
  CancelUploadResponse,
  ApiError,
} from '~/types/uploads';
import { useTokenInfo } from '~/composables/useTokenInfo';
import { useMetadata } from '~/composables/useMetadata';
import { validateSlot } from '~/utils/validation';
import { useTusUpload } from '~/composables/useTusUpload';
import { useUploadSlots } from '~/composables/useUploadSlots';
import { useUploadPolling } from '~/composables/useUploadPolling';
import { useStorage } from '@vueuse/core';

const route = useRoute();
const toast = useToast();
const token = ref(
  typeof route.query.token === 'string' ? route.query.token : String(route.params.token || ''),
);

const {
  tokenInfo,
  notFound,
  tokenError,
  isExpired,
  isDisabled,
  shareLinkText,
  shareLinkPath,
  fetchTokenInfo,
} = useTokenInfo(token);
const { metadataSchema, fetchMetadata, extractMetadata } = useMetadata();
const { startTusUpload, pauseUpload, resumeUpload } = useTusUpload();
const { slots, seedSlots, addSlot, unintiatedSlots } = useUploadSlots(metadataSchema);
const { pollUploadStatus, stopPolling, stopAllPolling } = useUploadPolling();

const notice = ref<string>('');
const loading = ref(true);

const results = ref<Record<number, any>>({});
const resumeTarget = ref<UploadRow | null>(null);
const resumeInput = ref<HTMLInputElement | null>(null);
const showNotice = useStorage<boolean>('show_notice', true);

const showForms = computed(
  () =>
    tokenInfo.value &&
    !isExpired.value &&
    !isDisabled.value &&
    (tokenInfo.value.remaining_uploads > 0 ||
      slots.value.some((s) => s.status && s.status !== 'completed')),
);
const canShare = computed(() =>
  Boolean(tokenInfo.value?.uploads?.some((upload) => upload.status === 'completed')),
);

const canAddMoreSlots = computed(
  () => tokenInfo.value && unintiatedSlots.value.length < (tokenInfo.value.remaining_uploads || 0),
);

const allRows = computed(() => {
  const completed = tokenInfo.value?.uploads || [];
  const active = slots.value
    .filter((s) => s.initiated)
    .map((s) => {
      const fileSize = s.file?.size ?? 0;
      const uploadedBytes = s.bytesUploaded ?? Math.floor((s.progress / 100) * fileSize);
      return {
        public_id: s.uploadId || '',
        filename: s.file?.name || '',
        status: s.status,
        upload_offset: uploadedBytes,
        upload_length: fileSize,
        size_bytes: fileSize,
        meta_data: s.values,
        slot: s,
        _reactiveKey: `${s.bytesUploaded}-${s.progress}-${s.status}`,
      };
    });

  const activeIds = new Set(active.map((a) => a.public_id));
  const nonDuplicateCompleted = completed.filter((c) => !activeIds.has(c.public_id));

  return [...active, ...nonDuplicateCompleted];
});

const acceptAttr = computed(() => {
  if (!tokenInfo.value?.allowed_mime || !tokenInfo.value.allowed_mime.length) return undefined;
  return tokenInfo.value.allowed_mime.join(',');
});

async function refreshAll() {
  try {
    await fetchTokenInfo();
    await fetchMetadata();
    seedSlots(tokenInfo.value);
  } finally {
    loading.value = false;
  }
}

function buildDefaultMetadataValues() {
  return Object.fromEntries(metadataSchema.value.map((field) => [field.key, field.default ?? '']));
}

async function onFile(slot: Slot, selectedFile: File | null) {
  const defaultValues = buildDefaultMetadataValues();

  slot.file = selectedFile;
  slot.values = defaultValues;
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value);

  if (!selectedFile) {
    return;
  }

  const extractedValues = await extractMetadata(selectedFile.name);
  if (slot.file !== selectedFile) {
    return;
  }

  const nextValues = { ...slot.values };
  Object.entries(extractedValues).forEach(([key, value]) => {
    if (slot.values[key] === defaultValues[key]) {
      nextValues[key] = value;
    }
  });
  slot.values = nextValues;
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value);
}

function onMetaChange(slot: Slot, values: Record<string, any>) {
  slot.values = values;
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value);
}

async function copyShareLink() {
  if (!shareLinkText.value || !canShare.value) return;
  copyText(shareLinkText.value);
  toast.add({
    title: 'Share link copied to clipboard',
    color: 'success',
    icon: 'i-lucide-circle-check',
  });
}

async function start(slot: Slot, idx: number) {
  if (!tokenInfo.value) {
    slot.error = 'Token missing or expired.';
    return;
  }
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value);
  if (!slot.file || slot.errors.length) {
    slot.error = slot.errors.join('; ') || 'Fill all metadata and select a file.';
    slot.status = 'validation_failed';
    return;
  }
  slot.error = '';
  slot.working = true;
  slot.status = 'initiating';
  try {
    const res = await $fetch<InitiateUploadResponse>(`/api/uploads/initiate`, {
      method: 'POST',
      query: { token: token.value },
      body: {
        meta_data: slot.values,
        filename: slot.file.name,
        filetype: slot.file.type,
        size_bytes: slot.file.size,
      },
    });
    results.value[idx] = res;
    slot.uploadId = res.upload_id;
    slot.initiated = true;

    // Decrement remaining_uploads locally since backend consumes upload on initiation
    if (tokenInfo.value && res.remaining_uploads !== undefined) {
      tokenInfo.value.remaining_uploads = res.remaining_uploads;
    }

    if (slot.file) {
      await startTusUpload(
        slot,
        res.upload_url,
        slot.file,
        token.value,
        tokenInfo.value,
        res.recommended_chunk_bytes,
        (completedSlot) => {
          if (completedSlot.status === 'postprocessing' && completedSlot.uploadId) {
            pollUploadStatus(completedSlot.uploadId, token.value, completedSlot, refreshAll);
          }
        },
      );
      await refreshAll();
    }
  } catch (err) {
    const error = err as ApiError;
    slot.error = error?.data?.detail || error?.message || 'Failed to initiate upload';
    slot.status = 'error';
  } finally {
    slot.working = false;
  }
}

function handlePause(row: UploadRowWithSlot) {
  if (row.slot) {
    pauseUpload(row.slot);
  }
}

function handleResume(row: UploadRowWithSlot) {
  if (row.slot) {
    resumeUpload(row.slot);
  } else {
    triggerResume(row);
  }
}

async function handleCancel(row: UploadRowWithSlot) {
  if (!row.public_id || row.status === 'completed') return;

  try {
    const res = await $fetch<CancelUploadResponse>(`/api/uploads/${row.public_id}/cancel`, {
      method: 'DELETE',
      query: { token: token.value },
    });

    if (tokenInfo.value && res.remaining_uploads !== undefined) {
      tokenInfo.value.remaining_uploads = res.remaining_uploads;
    }

    stopPolling(row.public_id);

    if (row.slot) {
      const slotIndex = slots.value.indexOf(row.slot);
      if (slotIndex > -1) {
        slots.value.splice(slotIndex, 1);
      }
    }

    toast.add({
      title: 'Upload cancelled',
      description: 'Upload slot has been restored',
      color: 'success',
      icon: 'i-lucide-circle-check',
    });

    await refreshAll();
  } catch (err) {
    const error = err as ApiError;
    toast.add({
      title: 'Failed to cancel upload',
      description: error?.data?.detail || error?.message || 'Unknown error',
      color: 'error',
      icon: 'i-lucide-triangle-alert',
    });
  }
}

function triggerResume(upload: UploadRow) {
  resumeTarget.value = upload;
  resumeInput.value?.click();
}

async function onResumeFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file || !resumeTarget.value || !resumeTarget.value.upload_url) {
    resumeTarget.value = null;
    return;
  }

  if (file.name !== resumeTarget.value.filename) {
    toast.add({
      title: 'File name mismatch',
      description: `Select ${resumeTarget.value.filename}; the selected file is ${file.name}.`,
      color: 'error',
      icon: 'i-lucide-triangle-alert',
    });
    if (resumeInput.value) resumeInput.value.value = '';
    resumeTarget.value = null;
    return;
  }

  const expectedSize = resumeTarget.value.upload_length;
  if (expectedSize === undefined || file.size !== expectedSize) {
    toast.add({
      title: 'File size mismatch',
      description:
        expectedSize === undefined
          ? 'The original upload size is unavailable.'
          : `${formatBytes(expectedSize)} expected; the selected file is ${formatBytes(file.size)}.`,
      color: 'error',
      icon: 'i-lucide-triangle-alert',
    });
    if (resumeInput.value) resumeInput.value.value = '';
    resumeTarget.value = null;
    return;
  }

  const resumeSlot = reactive<Slot>({
    file,
    values: resumeTarget.value.meta_data || {},
    error: '',
    working: true,
    progress: Math.round(
      ((resumeTarget.value.upload_offset || 0) / (resumeTarget.value.upload_length || 1)) * 100,
    ),
    bytesUploaded: resumeTarget.value.upload_offset || 0,
    status: 'resuming',
    errors: [],
    paused: false,
    initiated: true,
    uploadId: resumeTarget.value.public_id,
  });

  slots.value.push(resumeSlot);

  try {
    await startTusUpload(
      resumeSlot,
      resumeTarget.value.upload_url,
      file,
      token.value,
      tokenInfo.value,
      resumeTarget.value.recommended_chunk_bytes,
      (completedSlot) => {
        if (completedSlot.status === 'postprocessing' && completedSlot.uploadId) {
          pollUploadStatus(completedSlot.uploadId, token.value, completedSlot, refreshAll);
        }
      },
    );
    await refreshAll();
  } catch (err) {
    const error = err as ApiError;
    resumeSlot.error = error?.message || 'Resume failed';
    resumeSlot.status = 'error';
  } finally {
    if (resumeInput.value) resumeInput.value.value = '';
    resumeTarget.value = null;
  }
}

watch(
  () => route.query.token,
  (val) => {
    if (typeof val === 'string') {
      token.value = val;
      refreshAll();
    }
  },
);

onMounted(async () => {
  void refreshAll();

  const notice_req = await $fetch<{ notice: string | null }>('/api/notice/');
  if (notice_req.notice) {
    notice.value = notice_req.notice;
  }
});

onUnmounted(() => {
  stopAllPolling();
});
</script>
