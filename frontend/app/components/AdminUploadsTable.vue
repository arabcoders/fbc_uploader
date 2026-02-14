<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-12 rounded-lg ring ring-default bg-default">
      <UIcon name="i-heroicons-arrow-path" class="size-6 animate-spin text-muted" />
    </div>

    <div v-else-if="!uploads.length" class="flex items-center justify-center py-12 rounded-lg ring ring-default bg-default">
      <p class="text-sm text-muted">No uploads found</p>
    </div>

    <template v-else>
      <div class="block md:hidden space-y-3">
        <UCard v-for="upload in uploads" :key="upload.public_id">
          <template #header>
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0 flex-1">
                <NuxtLink v-if="upload.download_url" :href="getDownloadUrl(upload)" target="_blank"
                  class="font-medium hover:underline break-all" :aria-label="upload.filename">
                  {{ upload.filename || 'Unnamed file' }}
                </NuxtLink>
                <span v-else class="font-medium break-all">{{ upload.filename || 'Unnamed file' }}</span>
                <div class="text-xs text-muted mt-1">{{ upload.mimetype || 'Unknown type' }}</div>
              </div>
              <UBadge :color="upload.status === 'completed' ? 'success' : 'neutral'" variant="subtle" size="xs">
                {{ upload.status }}
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
                <UButton size="xs" color="neutral" variant="soft" icon="i-heroicons-information-circle-20-solid">
                  Metadata
                </UButton>
                <template #content>
                  <div class="space-y-3 text-sm min-w-64 max-w-96">
                    <div class="font-semibold text-highlighted">Metadata</div>
                    <div v-if="filterMetadata(upload.meta_data) && Object.keys(filterMetadata(upload.meta_data)).length" class="space-y-2">
                      <div v-for="(val, key) in filterMetadata(upload.meta_data)" :key="key" class="grid grid-cols-[auto_1fr] gap-2">
                        <span class="text-muted font-medium capitalize">{{ formatKey(String(key)) }}:</span>
                        <span class="wrap-break-word">{{ formatValue(val) }}</span>
                      </div>
                    </div>
                    <div v-else class="text-muted italic">No metadata</div>
                  </div>
                </template>
              </UPopover>

              <div class="flex-1"></div>

              <UButton size="xs" color="error" variant="soft" icon="i-heroicons-trash-20-solid"
                @click="$emit('delete', upload)">
                Delete
              </UButton>
            </div>
          </div>
        </UCard>
      </div>

      <div class="hidden md:block overflow-x-auto rounded-lg ring ring-default">
        <table class="w-full divide-y divide-default">
          <thead class="bg-elevated">
            <tr>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted min-w-64">File</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-32">Size</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-40">Uploaded</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-28">Status</th>
              <th class="px-4 py-3 text-right text-sm font-semibold text-highlighted w-32">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-default divide-y divide-default">
            <tr v-for="upload in uploads" :key="upload.public_id" class="hover:bg-elevated/50 transition-colors">
              <td class="px-4 py-3 text-sm">
                <div class="space-y-1">
                  <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
                    <NuxtLink v-if="upload.download_url" :href="getDownloadUrl(upload)" target="_blank"
                      class="font-medium hover:underline break-all cursor-pointer" :aria-label="upload.filename">
                      {{ upload.filename || 'Unnamed file' }}
                    </NuxtLink>
                    <span v-else class="font-medium break-all cursor-default">{{ upload.filename || 'Unnamed file' }}</span>
                    <template #content>
                      <div class="space-y-3 text-sm min-w-64 max-w-96">
                        <div class="font-semibold text-highlighted">Metadata</div>
                        <div v-if="filterMetadata(upload.meta_data) && Object.keys(filterMetadata(upload.meta_data)).length" class="space-y-2">
                          <div v-for="(val, key) in filterMetadata(upload.meta_data)" :key="key" class="grid grid-cols-[auto_1fr] gap-2">
                            <span class="text-muted font-medium capitalize">{{ formatKey(String(key)) }}:</span>
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
              <td class="px-4 py-3 text-sm font-medium">
                {{ formatBytes(upload.size_bytes || 0) }}
              </td>
              <td class="px-4 py-3 text-sm">
                {{ formatDate(upload.created_at as string) }}
              </td>
              <td class="px-4 py-3 text-sm">
                <UBadge :color="upload.status === 'completed' ? 'success' : 'neutral'" variant="subtle">
                  {{ upload.status }}
                </UBadge>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <UButton size="sm" color="error" variant="ghost" icon="i-heroicons-trash-20-solid"
                  @click="$emit('delete', upload)">
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
import type { UploadRow } from "~/types/uploads";
import { formatBytes, formatDate, formatKey, formatValue, addAdminKeyToUrl } from "~/utils";

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
  const { ffprobe, ...filtered } = meta_data;
  return filtered;
}

function getDownloadUrl(upload: UploadRow): string {
  if (!upload.download_url) return '';
  return addAdminKeyToUrl(upload.download_url, props.allowPublicDownloads, props.adminToken);
}
</script>
