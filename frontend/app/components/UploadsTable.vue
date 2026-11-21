<template>
  <div>
    <div class="block md:hidden space-y-3">
      <UCard v-for="(row, index) in rows" :key="row.public_id" variant="outline">
        <template #header>
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-xs text-muted">#{{ index + 1 }}</span>
                <UBadge :color="getStatusColor(row.status)" variant="soft" size="xs">
                  <span class="flex items-center gap-1.5">
                    <UIcon
                      :name="getStatusIcon(row.status)"
                      class="size-3.5 shrink-0"
                      :class="row.status === 'postprocessing' ? 'animate-spin' : ''"
                    />
                    <span>{{ formatUploadStatus(row.status) }}</span>
                  </span>
                </UBadge>
              </div>
              <a
                v-if="allowDownloads && row.download_url && row.status === 'completed'"
                :href="row.download_url"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium hover:underline break-all"
                :aria-label="row.filename"
              >
                {{ row.filename }}
              </a>
              <span v-else class="font-medium break-all">{{ row.filename }}</span>
            </div>
          </div>
        </template>

        <div class="space-y-3">
          <div class="space-y-2 text-sm">
            <div class="flex items-center justify-between">
              <span class="text-muted">Size</span>
              <span
                v-if="row.status === 'completed' || row.status === 'postprocessing'"
                class="font-medium"
              >
                {{ formatBytes(row.size_bytes ?? row.upload_length ?? 0) }}
              </span>
              <span v-else class="text-sm">
                <span class="font-medium">{{ formatBytes(row.upload_offset ?? 0) }}</span>
                <span class="text-muted"> / {{ formatBytes(row.upload_length ?? 0) }}</span>
              </span>
            </div>

            <div
              v-if="row.status !== 'completed' && row.status !== 'postprocessing'"
              class="space-y-1.5"
            >
              <div class="flex items-center justify-between">
                <span class="text-muted">Progress</span>
                <span class="text-sm text-muted">{{
                  percent(row.upload_offset, row.upload_length)
                }}</span>
              </div>
              <UProgress
                v-if="row.upload_length"
                :model-value="row.upload_offset ?? 0"
                :max="row.upload_length"
                size="xs"
                role="group"
                aria-label="Upload progress"
              />
            </div>
          </div>

          <div class="flex flex-wrap gap-2 pt-2 border-t border-default">
            <UPopover :ui="{ content: 'p-3' }">
              <UButton size="xs" color="neutral" variant="soft" icon="i-lucide-info">
                Metadata
              </UButton>
              <template #content>
                <div class="space-y-3 text-sm min-w-64 max-w-96">
                  <div class="font-semibold text-highlighted">Metadata</div>
                  <div
                    v-if="
                      filterMetadata(row.meta_data) &&
                      Object.keys(filterMetadata(row.meta_data)).length
                    "
                    class="space-y-2"
                  >
                    <div
                      v-for="(val, key) in filterMetadata(row.meta_data)"
                      :key="key"
                      class="grid grid-cols-[auto_1fr] gap-2"
                    >
                      <span class="text-muted font-medium capitalize">{{ formatKey(key) }}:</span>
                      <span class="wrap-break-word">{{ formatValue(val) }}</span>
                    </div>
                  </div>
                  <div v-else class="text-muted italic">No metadata</div>
                </div>
              </template>
            </UPopover>

            <div class="flex-1"></div>

            <UButton
              v-if="row.slot?.working && !row.slot?.paused"
              color="warning"
              variant="soft"
              size="xs"
              icon="i-lucide-pause"
              @click="$emit('pause', row)"
            >
              Pause
            </UButton>

            <UButton
              v-else-if="
                row.slot?.paused ||
                (row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0))
              "
              color="primary"
              variant="soft"
              size="xs"
              icon="i-lucide-play"
              @click="$emit('resume', row)"
            >
              Resume
            </UButton>

            <UButton
              v-else-if="!row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0)"
              color="primary"
              variant="soft"
              size="xs"
              icon="i-lucide-refresh-cw"
              @click="$emit('resume', row)"
            >
              Resume
            </UButton>

            <UButton
              v-if="
                row.status !== 'completed' &&
                (row.status === 'postprocessing' ||
                  (row.upload_offset ?? 0) < (row.upload_length ?? 0))
              "
              color="error"
              variant="soft"
              size="xs"
              icon="i-lucide-x"
              @click="$emit('cancel', row)"
            >
              Cancel
            </UButton>
          </div>
        </div>
      </UCard>
    </div>

    <div class="fbc-table-surface hidden md:block">
      <table class="fbc-table" aria-label="Uploads">
        <thead>
          <tr>
            <th scope="col" class="w-16">ID</th>
            <th scope="col" class="min-w-40">File</th>
            <th scope="col" class="w-32">Status</th>
            <th scope="col" class="w-56">Size</th>
            <th scope="col" class="w-32 text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="row.public_id">
            <td>{{ index + 1 }}</td>
            <td>
              <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
                <a
                  v-if="allowDownloads && row.download_url && row.status === 'completed'"
                  :href="row.download_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="font-medium hover:underline break-all cursor-pointer px-2 py-1 rounded hover:bg-elevated/50 inline-block"
                  :aria-label="row.filename"
                >
                  {{ row.filename }}
                </a>
                <UButton
                  v-else
                  variant="ghost"
                  color="neutral"
                  size="xs"
                  class="w-full justify-start break-all"
                  :aria-label="row.filename"
                >
                  <span class="break-all text-left">{{ row.filename }}</span>
                </UButton>
                <template #content>
                  <div class="space-y-3 text-sm min-w-64 max-w-96">
                    <div class="font-semibold text-highlighted">Metadata</div>
                    <div
                      v-if="
                        filterMetadata(row.meta_data) &&
                        Object.keys(filterMetadata(row.meta_data)).length
                      "
                      class="space-y-2"
                    >
                      <div
                        v-for="(val, key) in filterMetadata(row.meta_data)"
                        :key="key"
                        class="grid grid-cols-[auto_1fr] gap-2"
                      >
                        <span class="text-muted font-medium capitalize">{{ formatKey(key) }}:</span>
                        <span class="wrap-break-word">{{ formatValue(val) }}</span>
                      </div>
                    </div>
                    <div v-else class="text-muted italic">No metadata</div>
                  </div>
                </template>
              </UPopover>
            </td>
            <td>
              <UBadge :color="getStatusColor(row.status)" variant="soft">
                <span class="flex items-center gap-1.5">
                  <UIcon
                    :name="getStatusIcon(row.status)"
                    class="size-3.5 shrink-0"
                    :class="row.status === 'postprocessing' ? 'animate-spin' : ''"
                  />
                  <span>{{ formatUploadStatus(row.status) }}</span>
                </span>
              </UBadge>
            </td>
            <td class="whitespace-nowrap tabular-nums">
              <span
                v-if="row.status === 'completed' || row.status === 'postprocessing'"
                class="font-medium"
              >
                {{ formatBytes(row.size_bytes ?? row.upload_length ?? 0) }}
              </span>
              <div v-else class="space-y-1.5">
                <div>
                  <span class="font-medium">{{ formatBytes(row.upload_offset ?? 0) }}</span>
                  <span class="text-muted"> / {{ formatBytes(row.upload_length ?? 0) }}</span>
                  <span class="text-muted ml-1"
                    >({{ percent(row.upload_offset, row.upload_length) }})</span
                  >
                </div>
                <UProgress
                  v-if="row.upload_length"
                  :model-value="row.upload_offset ?? 0"
                  :max="row.upload_length"
                  size="xs"
                  role="group"
                  aria-label="Upload progress"
                />
              </div>
            </td>
            <td>
              <div class="flex gap-2 justify-end">
                <UButton
                  v-if="row.slot?.working && !row.slot?.paused"
                  color="warning"
                  variant="soft"
                  size="xs"
                  icon="i-lucide-pause"
                  @click="$emit('pause', row)"
                >
                  Pause
                </UButton>

                <UButton
                  v-else-if="
                    row.slot?.paused ||
                    (row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0))
                  "
                  color="primary"
                  variant="soft"
                  size="xs"
                  icon="i-lucide-play"
                  @click="$emit('resume', row)"
                >
                  Resume
                </UButton>

                <UButton
                  v-else-if="!row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0)"
                  color="primary"
                  variant="soft"
                  size="xs"
                  icon="i-lucide-refresh-cw"
                  @click="$emit('resume', row)"
                >
                  Resume
                </UButton>

                <UButton
                  v-if="
                    row.status !== 'completed' &&
                    (row.status === 'postprocessing' ||
                      (row.upload_offset ?? 0) < (row.upload_length ?? 0))
                  "
                  color="error"
                  variant="soft"
                  size="xs"
                  icon="i-lucide-x"
                  @click="$emit('cancel', row)"
                >
                  Cancel
                </UButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UploadRow, Slot } from '../types/uploads';
import { percent, formatKey, formatUploadStatus, formatValue, formatBytes } from '../utils';

type UploadRowExt = UploadRow & {
  share_preview?: string;
  title_display?: string;
  source_display?: string;
  slot?: Slot;
};

defineProps<{
  rows: UploadRowExt[];
  allowDownloads?: boolean;
}>();

defineEmits<{ resume: [UploadRowExt]; pause: [UploadRowExt]; cancel: [UploadRowExt] }>();

function getStatusColor(status: string): 'success' | 'error' | 'warning' | 'primary' | 'neutral' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'error':
    case 'validation_failed':
      return 'error';
    case 'paused':
      return 'warning';
    case 'uploading':
    case 'in_progress':
    case 'postprocessing':
    case 'initiating':
      return 'primary';
    default:
      return 'neutral';
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'completed':
      return 'i-lucide-circle-check';
    case 'error':
    case 'validation_failed':
      return 'i-lucide-circle-alert';
    case 'paused':
      return 'i-lucide-circle-pause';
    case 'uploading':
    case 'in_progress':
      return 'i-lucide-refresh-cw';
    case 'postprocessing':
      return 'i-lucide-settings';
    case 'initiating':
      return 'i-lucide-upload';
    case 'pending':
      return 'i-lucide-clock';
    default:
      return 'i-lucide-circle-help';
  }
}

function filterMetadata(meta_data: Record<string, any> | undefined): Record<string, any> {
  if (!meta_data) return {};
  const { ffprobe, upload_checksums, ...filtered } = meta_data;
  return filtered;
}
</script>
