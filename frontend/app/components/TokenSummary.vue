<template>
  <div v-if="tokenInfo" class="flex items-center justify-between gap-4 flex-wrap">
    <div class="flex items-center gap-4 flex-wrap text-sm">
      <div class="flex items-center gap-2">
        <UIcon name="i-heroicons-rectangle-stack-20-solid" class="text-muted" />
        <span class="text-muted">Remaining uploads:</span>
        <UBadge color="primary" variant="soft">{{ tokenInfo.remaining_uploads }} / {{ tokenInfo.max_uploads }}</UBadge>
      </div>
      <div v-if="tokenInfo.max_size_bytes" class="flex items-center gap-2">
        <UIcon name="i-heroicons-scale-20-solid" class="text-muted" />
        <span class="text-muted">Max size:</span>
        <span class="font-medium">{{ formatBytes(tokenInfo.max_size_bytes) }}</span>
      </div>
      <div class="flex items-center gap-2">
        <UIcon name="i-heroicons-clock-20-solid" class="text-muted" />
        <span class="text-muted">Expires:</span>
        <span class="font-medium">{{ formatDate(tokenInfo.expires_at) }}</span>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <UButton v-if="shareLink" size="xs" color="primary" variant="outline" icon="i-heroicons-clipboard"
        @click="$emit('copy')">
        Copy share link
      </UButton>
      <UButton size="xs" color="neutral" variant="ghost" icon="i-heroicons-arrow-path" @click="$emit('refresh')">
        Refresh
      </UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TokenInfo } from "../types/token";
import { formatBytes, formatDate } from "../utils";

defineProps<{
  tokenInfo: TokenInfo | null;
  shareLink: string;
}>();

defineEmits<{
  refresh: [];
  copy: [];
}>();
</script>
