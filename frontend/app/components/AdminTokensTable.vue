<template>
  <div class="overflow-x-auto rounded-lg ring ring-default">
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
        <tr v-if="loading">
          <td colspan="6" class="px-4 py-12 text-center">
            <UIcon name="i-heroicons-arrow-path" class="size-6 animate-spin mx-auto text-muted" />
          </td>
        </tr>
        <tr v-else-if="!tokens.length">
          <td colspan="6" class="px-4 py-12 text-center text-sm text-muted">
            No tokens found
          </td>
        </tr>
        <tr v-else v-for="token in tokens" :key="token.token" class="hover:bg-elevated/50 transition-colors">
          <td class="px-4 py-3 text-sm">
            <div class="space-y-1.5">
              <div class="flex items-center gap-2">
                <template v-if="token.disabled">
                  <span>{{ token.token }}</span>
                  <UTooltip text="Token is disabled" :arrow="true">
                    <UIcon name="i-heroicons-lock-closed-20-solid" class="size-4 text-muted" />
                  </UTooltip>
                </template>
                <template v-else>
                  <NuxtLink :to="`/t/${token.token}`">{{ token.token }}</NuxtLink>
                  <UTooltip text="Copy Token URL" :arrow="true">
                    <UButton size="xs" color="neutral" variant="ghost" icon="i-heroicons-clipboard-document-20-solid"
                      aria-label="Copy upload token" @click="copyUrl(token.token)" />
                  </UTooltip>
                </template>
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
              <UButton size="sm" color="neutral" variant="ghost" icon="i-heroicons-folder-open-20-solid"
                @click="$emit('viewUploads', token)" />
              <UButton size="sm" color="neutral" variant="ghost" icon="i-heroicons-pencil-square-20-solid"
                @click="$emit('edit', token)" />
              <UButton size="sm" color="error" variant="ghost" icon="i-heroicons-trash-20-solid"
                @click="$emit('delete', token)" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { AdminToken } from "~/types/token";
import { copyText, formatBytes, formatDate } from "~/utils";

defineProps<{
  tokens: AdminToken[];
  loading?: boolean;
}>();

defineEmits<{
  viewUploads: [token: AdminToken];
  edit: [token: AdminToken];
  delete: [token: AdminToken];
}>();

const copyUrl = (token: string) => {
  const url = `${window.location.origin}/t/${token}`;
  copyText(url);
}
</script>
