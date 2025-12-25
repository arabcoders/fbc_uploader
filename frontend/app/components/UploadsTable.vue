<template>
  <div class="overflow-x-auto rounded-lg ring ring-default">
    <table class="w-full divide-y divide-default">
      <thead class="bg-elevated">
        <tr>
          <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-20">ID</th>
          <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted min-w-48">File</th>
          <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-32">Status</th>
          <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-40">Size</th>
          <th class="px-4 py-3 text-right text-sm font-semibold text-highlighted w-32">Actions</th>
        </tr>
      </thead>
      <tbody class="bg-default divide-y divide-default">
        <tr v-for="row in rows" :key="row.id" class="hover:bg-elevated/50 transition-colors">
          <td class="px-4 py-3 text-sm">{{ row.id }}</td>
          <td class="px-4 py-3 text-sm">
            <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
              <NuxtLink v-if="allowDownloads && row.download_url && row.status === 'completed'" :href="row.download_url" target="_blank"
                class="font-medium hover:underline break-all cursor-pointer px-2 py-1 rounded hover:bg-elevated/50 inline-block"
                :aria-label="row.filename">
                {{ row.filename }}
              </NuxtLink>
              <UButton v-else variant="ghost" color="neutral" size="xs" class="w-full justify-start break-all"
                :aria-label="row.filename">
                <span class="break-all text-left">{{ row.filename }}</span>
              </UButton>
              <template #content>
                <div class="space-y-3 text-sm min-w-64 max-w-96">
                  <div class="font-semibold text-highlighted">Metadata</div>
                  <div v-if="row.meta_data && Object.keys(row.meta_data).length" class="space-y-2">
                    <div v-for="(val, key) in row.meta_data" :key="key" class="grid grid-cols-[auto_1fr] gap-2">
                      <span class="text-muted font-medium capitalize">{{ formatKey(key) }}:</span>
                      <span class="wrap-break-word">{{ formatValue(val) }}</span>
                    </div>
                  </div>
                  <div v-else class="text-muted italic">No metadata</div>
                </div>
              </template>
            </UPopover>
          </td>
          <td class="px-4 py-3 text-sm">
            <UBadge 
              :color="getStatusColor(row.status)" 
              variant="soft"
              :icon="getStatusIcon(row.status)">
              {{ row.status }}
            </UBadge>
          </td>
          <td class="px-4 py-3 text-sm">
            <span v-if="row.status === 'completed'" class="font-medium">
              {{ formatBytes(row.size_bytes ?? row.upload_length ?? 0) }}
            </span>
            <span v-else class="text-sm">
              <span class="font-medium">{{ formatBytes(row.upload_offset ?? 0) }}</span>
              <span class="text-muted"> / {{ formatBytes(row.upload_length ?? 0) }}</span>
              <span class="text-muted ml-1">({{ percent(row.upload_offset, row.upload_length) }})</span>
            </span>
          </td>
          <td class="px-4 py-3 text-sm text-right">
            <div class="flex gap-2 justify-end">
              
              <UButton v-if="row.slot?.working && !row.slot?.paused" color="warning" variant="soft" size="xs"
                icon="i-heroicons-pause-20-solid" @click="$emit('pause', row)">
                Pause
              </UButton>
              
              <UButton v-else-if="row.slot?.paused || (row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0))"
                color="primary" variant="soft" size="xs" icon="i-heroicons-play-20-solid" @click="$emit('resume', row)">
                Resume
              </UButton>
              
              <UButton v-else-if="!row.slot && (row.upload_offset ?? 0) < (row.upload_length ?? 0)" color="primary"
                variant="soft" size="xs" icon="i-heroicons-arrow-path" @click="$emit('resume', row)">
                Resume
              </UButton>
              
              <UButton v-if="row.status !== 'completed' && (row.upload_offset ?? 0) < (row.upload_length ?? 0)"
                color="error" variant="soft" size="xs" icon="i-heroicons-x-mark-20-solid" @click="$emit('cancel', row)">
                Cancel
              </UButton>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { UploadRow, Slot } from "../types/uploads";
import { percent, formatKey, formatValue, formatBytes } from "../utils";

type UploadRowExt = UploadRow & { share_preview?: string; title_display?: string; source_display?: string; slot?: Slot };

defineProps<{
  rows: UploadRowExt[];
  allowDownloads?: boolean;
}>();

defineEmits<{ resume: [UploadRowExt]; pause: [UploadRowExt]; cancel: [UploadRowExt]; }>();

function getStatusColor(status: string): 'success' | 'error' | 'warning' | 'primary' | 'neutral' {
  switch (status) {
    case 'completed': return 'success';
    case 'error': 
    case 'validation_failed': return 'error';
    case 'paused': return 'warning';
    case 'uploading':
    case 'in_progress':
    case 'initiating': return 'primary';
    default: return 'neutral';
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'completed': return 'i-heroicons-check-circle-20-solid';
    case 'error':
    case 'validation_failed': return 'i-heroicons-exclamation-circle-20-solid';
    case 'paused': return 'i-heroicons-pause-circle-20-solid';
    case 'uploading':
    case 'in_progress': return 'i-heroicons-arrow-path-20-solid';
    case 'initiating': return 'i-heroicons-arrow-up-tray-20-solid';
    case 'pending': return 'i-heroicons-clock-20-solid';
    default: return 'i-heroicons-question-mark-circle-20-solid';
  }
}
</script>
