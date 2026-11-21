<template>
  <div>
    <div v-if="loading" class="space-y-3" role="status">
      <span class="sr-only">Loading uploads</span>
      <USkeleton v-for="row in 3" :key="row" class="h-12 w-full" />
    </div>

    <UEmpty
      v-else-if="!uploads.length"
      icon="i-lucide-inbox"
      title="No uploads"
      description="Files uploaded with this token will appear here."
    />

    <template v-else>
      <div class="block md:hidden space-y-3">
        <UCard v-for="upload in uploads" :key="upload.public_id">
          <template #header>
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0 flex-1">
                <a
                  v-if="upload.download_url"
                  :href="getDownloadUrl(upload)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="font-medium hover:underline break-all"
                  :aria-label="upload.filename"
                >
                  {{ upload.filename || 'Unnamed file' }}
                </a>
                <span v-else class="font-medium break-all">{{
                  upload.filename || 'Unnamed file'
                }}</span>
                <div class="text-xs text-muted mt-1">{{ upload.mimetype || 'Unknown type' }}</div>
              </div>
              <UBadge
                :color="upload.status === 'completed' ? 'success' : 'neutral'"
                variant="subtle"
                size="xs"
              >
                {{ formatUploadStatus(upload.status) }}
              </UBadge>
            </div>
          </template>

          <div class="space-y-3">
            <div class="space-y-2 text-sm">
              <div class="flex items-center justify-between">
                <span class="text-muted">Size</span>
                <span class="font-medium">{{ formatBytes(upload.size_bytes || 0) }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-muted">Uploaded</span>
                <span>{{ formatDate(upload.created_at as string) }}</span>
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
                        filterMetadata(upload.meta_data) &&
                        Object.keys(filterMetadata(upload.meta_data)).length
                      "
                      class="space-y-2"
                    >
                      <div
                        v-for="(val, key) in filterMetadata(upload.meta_data)"
                        :key="key"
                        class="grid grid-cols-[auto_1fr] gap-2"
                      >
                        <span class="text-muted font-medium capitalize"
                          >{{ formatKey(String(key)) }}:</span
                        >
                        <span class="wrap-break-word">{{ formatValue(val) }}</span>
                      </div>
                    </div>
                    <div v-else class="text-muted italic">No metadata</div>
                  </div>
                </template>
              </UPopover>

              <div class="flex-1"></div>

              <UButton
                size="xs"
                color="error"
                variant="soft"
                icon="i-lucide-trash-2"
                @click="$emit('delete', upload)"
              >
                Delete
              </UButton>
            </div>
          </div>
        </UCard>
      </div>

      <div class="fbc-table-surface hidden md:block">
        <table class="fbc-table" aria-label="Uploaded files">
          <thead>
            <tr>
              <th scope="col" class="min-w-48">File</th>
              <th scope="col" class="w-24">Size</th>
              <th scope="col" class="w-40">Uploaded</th>
              <th scope="col" class="w-28">Status</th>
              <th scope="col" class="w-28 text-end">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="upload in uploads" :key="upload.public_id">
              <td>
                <div class="space-y-1">
                  <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
                    <a
                      v-if="upload.download_url"
                      :href="getDownloadUrl(upload)"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="font-medium hover:underline break-all cursor-pointer"
                      :aria-label="upload.filename"
                    >
                      {{ upload.filename || 'Unnamed file' }}
                    </a>
                    <span v-else class="font-medium break-all cursor-default">{{
                      upload.filename || 'Unnamed file'
                    }}</span>
                    <template #content>
                      <div class="space-y-3 text-sm min-w-64 max-w-96">
                        <div class="font-semibold text-highlighted">Metadata</div>
                        <div
                          v-if="
                            filterMetadata(upload.meta_data) &&
                            Object.keys(filterMetadata(upload.meta_data)).length
                          "
                          class="space-y-2"
                        >
                          <div
                            v-for="(val, key) in filterMetadata(upload.meta_data)"
                            :key="key"
                            class="grid grid-cols-[auto_1fr] gap-2"
                          >
                            <span class="text-muted font-medium capitalize"
                              >{{ formatKey(String(key)) }}:</span
                            >
                            <span class="wrap-break-word">{{ formatValue(val) }}</span>
                          </div>
                        </div>
                        <div v-else class="text-muted italic">No metadata</div>
                      </div>
                    </template>
                  </UPopover>
                  <div class="text-xs text-muted">{{ upload.mimetype || 'Unknown type' }}</div>
                </div>
              </td>
              <td class="font-medium">
                {{ formatBytes(upload.size_bytes || 0) }}
              </td>
              <td>
                {{ formatDate(upload.created_at as string) }}
              </td>
              <td>
                <UBadge
                  :color="upload.status === 'completed' ? 'success' : 'neutral'"
                  variant="subtle"
                >
                  {{ formatUploadStatus(upload.status) }}
                </UBadge>
              </td>
              <td class="text-end">
                <UButton
                  size="sm"
                  color="error"
                  variant="ghost"
                  icon="i-lucide-trash-2"
                  @click="$emit('delete', upload)"
                >
                  Delete
                </UButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { UploadRow } from '~/types/uploads';
import {
  addAdminKeyToUrl,
  formatBytes,
  formatDate,
  formatKey,
  formatUploadStatus,
  formatValue,
} from '~/utils';

const props = defineProps<{
  uploads: UploadRow[];
  loading?: boolean;
  allowPublicDownloads: boolean;
  adminToken: string | null;
}>();

defineEmits<{
  delete: [upload: UploadRow];
}>();

function filterMetadata(meta_data: Record<string, any> | undefined): Record<string, any> {
  if (!meta_data) return {};
  const { ffprobe, upload_checksums, ...filtered } = meta_data;
  return filtered;
}

function getDownloadUrl(upload: UploadRow): string {
  if (!upload.download_url) return '';
  return addAdminKeyToUrl(upload.download_url, props.allowPublicDownloads, props.adminToken);
}
</script>
