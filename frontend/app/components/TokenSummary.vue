<template>
  <div v-if="tokenInfo" class="flex flex-wrap items-center justify-between gap-4">
    <div class="flex items-center gap-4 flex-wrap text-sm">
      <div class="flex items-center gap-2">
        <UIcon name="i-lucide-layers" class="size-4 text-muted" />
        <span class="text-muted">Remaining uploads:</span>
        <UBadge color="primary" variant="soft"
          >{{ tokenInfo.remaining_uploads }} / {{ tokenInfo.max_uploads }}</UBadge
        >
      </div>
      <div v-if="tokenInfo.max_size_bytes" class="flex items-center gap-2">
        <UIcon name="i-lucide-scale" class="size-4 text-muted" />
        <span class="text-muted">Max size:</span>
        <span class="font-medium">{{ formatBytes(tokenInfo.max_size_bytes) }}</span>
      </div>
      <div class="flex items-center gap-2">
        <UIcon name="i-lucide-clock" class="size-4 text-muted" />
        <span class="text-muted">Expires:</span>
        <span class="font-medium">{{ formatDate(tokenInfo.expires_at) }}</span>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <UButton
        v-if="sharePath && !shareDisabled"
        :to="sharePath"
        color="neutral"
        variant="outline"
        icon="i-lucide-external-link"
        label="Open share page"
      />
      <UButton
        v-if="shareLink"
        color="neutral"
        variant="outline"
        icon="i-lucide-copy"
        :disabled="shareDisabled"
        @click="$emit('copy')"
      >
        Copy share link
      </UButton>
      <UButton color="neutral" variant="ghost" icon="i-lucide-refresh-cw" @click="$emit('refresh')">
        Refresh
      </UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TokenInfo } from '../types/token';
import { formatBytes, formatDate } from '../utils';

defineProps<{
  tokenInfo: TokenInfo | null;
  shareLink: string;
  sharePath: string;
  shareDisabled: boolean;
}>();

defineEmits<{
  refresh: [];
  copy: [];
}>();
</script>
