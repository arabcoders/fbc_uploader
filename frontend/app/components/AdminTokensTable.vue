<template>
  <div>
    <div v-if="loading && !tokens.length" class="space-y-3" role="status">
      <span class="sr-only">Loading tokens</span>
      <USkeleton v-for="row in 3" :key="row" class="h-12 w-full" />
    </div>

    <UEmpty
      v-else-if="!tokens.length"
      icon="i-lucide-link"
      title="No upload tokens"
      description="Create a token to give someone an upload link."
    />

    <template v-else>
      <ul class="divide-y divide-default border-y border-default md:hidden" :aria-busy="loading">
        <li v-for="token in tokens" :key="token.token" class="space-y-2.5 py-3">
          <div class="flex items-start justify-between gap-3">
            <NuxtLink
              :to="`/${token.disabled ? 'f' : 't'}/${token.token}`"
              class="font-mono text-sm font-medium wrap-anywhere text-highlighted hover:underline"
            >
              {{ token.token }}
            </NuxtLink>
            <UBadge :color="token.disabled ? 'neutral' : 'success'" variant="soft" size="xs">
              {{ token.disabled ? 'Disabled' : 'Active' }}
            </UBadge>
          </div>

          <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
            <dt class="text-muted">Usage</dt>
            <dd class="tabular-nums">
              {{ token.uploads_used }} / {{ token.max_uploads }}
              <span class="ml-1 text-muted">· {{ token.remaining_uploads }} left</span>
            </dd>
            <dt class="text-muted">Max size</dt>
            <dd>{{ formatBytes(token.max_size_bytes) }}</dd>
            <dt class="text-muted">Expires</dt>
            <dd>{{ formatDate(token.expires_at) || 'N/A' }}</dd>
          </dl>

          <div class="-ms-2 flex flex-wrap gap-0.5">
            <UDropdownMenu :items="getCopyMenuItems(token)">
              <UButton
                color="neutral"
                variant="ghost"
                icon="i-lucide-copy"
                label="Copy"
                aria-label="Copy links"
              />
            </UDropdownMenu>
            <UButton
              color="neutral"
              variant="ghost"
              icon="i-lucide-folder-open"
              label="Files"
              aria-label="View uploads"
              @click="$emit('viewUploads', token)"
            />
            <UButton
              color="neutral"
              variant="ghost"
              icon="i-lucide-pencil"
              label="Edit"
              @click="$emit('edit', token)"
            />
            <UButton
              color="error"
              variant="ghost"
              icon="i-lucide-trash-2"
              label="Delete"
              @click="$emit('delete', token)"
            />
          </div>
        </li>
      </ul>

      <div class="hidden overflow-x-auto md:block">
        <table
          class="fbc-table border-y border-default"
          aria-label="Upload tokens"
          :aria-busy="loading"
        >
          <thead>
            <tr>
              <th scope="col" class="min-w-32">Token</th>
              <th scope="col" class="w-32">Usage</th>
              <th scope="col" class="w-24">Max size</th>
              <th scope="col" class="w-40 xl:w-52">Expires</th>
              <th scope="col" class="w-24">Status</th>
              <th scope="col" class="w-36 text-end">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="token in tokens" :key="token.token">
              <td>
                <NuxtLink
                  :to="`/${token.disabled ? 'f' : 't'}/${token.token}`"
                  class="font-mono font-medium wrap-anywhere text-highlighted hover:underline"
                >
                  {{ token.token }}
                </NuxtLink>
              </td>
              <td class="whitespace-nowrap tabular-nums">
                {{ token.uploads_used }} / {{ token.max_uploads }}
                <span class="ml-1 text-xs text-muted">· {{ token.remaining_uploads }} left</span>
              </td>
              <td class="whitespace-nowrap tabular-nums">
                {{ formatBytes(token.max_size_bytes) }}
              </td>
              <td class="text-toned xl:whitespace-nowrap">
                {{ formatDate(token.expires_at) || 'N/A' }}
              </td>
              <td>
                <UBadge :color="token.disabled ? 'neutral' : 'success'" variant="soft">
                  {{ token.disabled ? 'Disabled' : 'Active' }}
                </UBadge>
              </td>
              <td>
                <div class="flex items-center gap-1 justify-end">
                  <UDropdownMenu :items="getCopyMenuItems(token)" :content="{ align: 'end' }">
                    <UButton
                      color="neutral"
                      variant="ghost"
                      icon="i-lucide-copy"
                      aria-label="Copy link"
                      title="Copy link"
                    />
                  </UDropdownMenu>
                  <UTooltip text="View Uploads" :arrow="true">
                    <UButton
                      size="sm"
                      color="neutral"
                      variant="ghost"
                      icon="i-lucide-folder-open"
                      aria-label="View uploads"
                      @click="$emit('viewUploads', token)"
                    />
                  </UTooltip>

                  <UTooltip text="Edit token" :arrow="true">
                    <UButton
                      size="sm"
                      color="neutral"
                      variant="ghost"
                      icon="i-lucide-pencil"
                      aria-label="Edit token"
                      @click="$emit('edit', token)"
                    />
                  </UTooltip>

                  <UTooltip text="Delete token" :arrow="true">
                    <UButton
                      size="sm"
                      color="error"
                      variant="ghost"
                      icon="i-lucide-trash-2"
                      aria-label="Delete token"
                      @click="$emit('delete', token)"
                    />
                  </UTooltip>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { AdminToken } from '~/types/token';
import { copyText, formatBytes, formatDate } from '~/utils';

const toast = useToast();

defineProps<{
  tokens: AdminToken[];
  loading?: boolean;
}>();

defineEmits<{
  viewUploads: [token: AdminToken];
  edit: [token: AdminToken];
  delete: [token: AdminToken];
}>();

const copyUrl = (path: string, token: string) => {
  const url = `${window.location.origin}/${path}/${token}`;
  copyText(url);
  toast.add({
    title: 'Link copied to clipboard',
    color: 'success',
    icon: 'i-lucide-circle-check',
  });
};

const getCopyMenuItems = (token: AdminToken) => [
  [
    {
      label: 'Copy upload link',
      icon: 'i-lucide-upload',
      onSelect: () => copyUrl('t', token.token),
    },
  ],
  [
    {
      label: 'Copy share link',
      icon: 'i-lucide-share-2',
      onSelect: () => copyUrl('f', token.download_token),
    },
  ],
];
</script>
