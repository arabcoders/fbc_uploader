<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-12 rounded-lg ring ring-default bg-default">
      <UIcon name="i-heroicons-arrow-path" class="size-6 animate-spin text-muted" />
    </div>

    <div v-else-if="!tokens.length" class="flex items-center justify-center py-12 rounded-lg ring ring-default bg-default">
      <p class="text-sm text-muted">No tokens found</p>
    </div>

    <template v-else>
      <div class="block md:hidden space-y-3">
        <UCard v-for="token in tokens" :key="token.token">
          <template #header>
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <NuxtLink :to="`/${token.disabled ? 'f' : 't'}/${token.token}`" class="font-medium truncate">
                  {{ token.token }}
                </NuxtLink>
                <UIcon v-if="token.disabled" name="i-heroicons-lock-closed-20-solid" class="size-4 text-muted flex-shrink-0" />
              </div>
              <UBadge :color="token.disabled ? 'neutral' : 'success'" variant="subtle" size="xs">
                {{ token.disabled ? 'Disabled' : 'Active' }}
              </UBadge>
            </div>
          </template>

          <div class="space-y-3">
            <div class="space-y-2 text-sm">
              <div class="flex items-center justify-between">
                <span class="text-muted">Usage</span>
                <div class="flex flex-col items-end gap-1">
                  <UBadge color="primary" variant="subtle" size="xs">
                    {{ token.uploads_used }} / {{ token.max_uploads }}
                  </UBadge>
                  <span class="text-xs text-muted">{{ token.remaining_uploads }} remaining</span>
                </div>
              </div>
              
              <div class="flex items-center justify-between">
                <span class="text-muted">Max size</span>
                <span class="font-medium">{{ formatBytes(token.max_size_bytes) }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-muted">Expires</span>
                <span :class="token.disabled ? 'text-muted' : ''">
                  {{ formatDate(token.expires_at as string) || '—' }}
                </span>
              </div>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t border-default">
              <UDropdownMenu :items="getCopyMenuItems(token)">
                <UButton size="xs" color="neutral" variant="soft" icon="i-heroicons-clipboard-document-20-solid">
                  Copy
                </UButton>
              </UDropdownMenu>
              
              <UButton size="xs" color="neutral" variant="soft" icon="i-heroicons-folder-open-20-solid"
                @click="$emit('viewUploads', token)">
                View
              </UButton>

              <UButton size="xs" color="neutral" variant="soft" icon="i-heroicons-pencil-square-20-solid"
                @click="$emit('edit', token)">
                Edit
              </UButton>

              <UButton size="xs" color="error" variant="soft" icon="i-heroicons-trash-20-solid"
                @click="$emit('delete', token)">
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
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted min-w-48">Token</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-40">Usage</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-32">Max size</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-40">Expires</th>
              <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-24">Status</th>
              <th class="px-4 py-3 text-right text-sm font-semibold text-highlighted w-48">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-default divide-y divide-default">
            <tr v-for="token in tokens" :key="token.token" class="hover:bg-elevated/50 transition-colors">
              <td class="px-4 py-3 text-sm">
                <div class="space-y-1.5">
                  <div class="flex items-center gap-2">
                    <NuxtLink :to="`/${token.disabled ? 'f' : 't'}/${token.token}`">{{ token.token }}</NuxtLink>
                    <UTooltip text="Token is disabled" :arrow="true" v-if="token.disabled">
                      <UIcon name="i-heroicons-lock-closed-20-solid" class="size-4 text-muted" />
                    </UTooltip>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-sm">
                <div class="space-y-1">
                  <UBadge color="primary" variant="subtle" size="md">
                    {{ token.uploads_used }} / {{ token.max_uploads }}
                  </UBadge>
                  <p class="text-xs text-muted">{{ token.remaining_uploads }} remaining</p>
                </div>
              </td>
              <td class="px-4 py-3 text-sm font-medium">
                {{ formatBytes(token.max_size_bytes) }}
              </td>
              <td class="px-4 py-3 text-sm" :class="token.disabled ? 'text-muted' : ''">
                {{ formatDate(token.expires_at as string) || '—' }}
              </td>
              <td class="px-4 py-3 text-sm">
                <UBadge :color="token.disabled ? 'neutral' : 'success'" variant="subtle">
                  {{ token.disabled ? 'Disabled' : 'Active' }}
                </UBadge>
              </td>
              <td class="px-4 py-3 text-sm text-right">
                <div class="flex items-center gap-1 justify-end">
                  <UDropdownMenu :items="getCopyMenuItems(token)" :content="{ align: 'end' }">
                    <UTooltip text="Copy link" :arrow="true">
                      <UButton size="sm" color="neutral" variant="ghost" icon="i-heroicons-clipboard-document-20-solid" />
                    </UTooltip>
                  </UDropdownMenu>
                  <UTooltip text="View Uploads" :arrow="true">
                    <UButton size="sm" color="neutral" variant="ghost" icon="i-heroicons-folder-open-20-solid"
                      @click="$emit('viewUploads', token)" />
                  </UTooltip>

                  <UTooltip text="Edit token" :arrow="true">
                    <UButton size="sm" color="neutral" variant="ghost" icon="i-heroicons-pencil-square-20-solid"
                      @click="$emit('edit', token)" />
                  </UTooltip>

                  <UTooltip text="Delete token" :arrow="true">
                    <UButton size="sm" color="error" variant="ghost" icon="i-heroicons-trash-20-solid"
                      @click="$emit('delete', token)" />
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
import type { AdminToken } from "~/types/token";
import { copyText, formatBytes, formatDate } from "~/utils";

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
  console.log("Copying URL:", url);
  copyText(url);
  toast.add({
    title: 'link copied to clipboard.',
    color: 'success',
    icon: 'i-heroicons-check-circle-20-solid',
  })
}

const getCopyMenuItems = (token: AdminToken) => [
  [{
    label: 'Copy upload link',
    icon: 'i-heroicons-arrow-up-tray-20-solid',
    onSelect: () => copyUrl("t", token.token)
  }],
  [{
    label: 'Copy share link',
    icon: 'i-heroicons-share-20-solid',
    onSelect: () => copyUrl("f", token.download_token)
  }]
]
</script>