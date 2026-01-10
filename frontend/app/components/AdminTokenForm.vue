<template>
  <form class="space-y-4" @submit.prevent="handleSubmit">
    <div class="grid gap-4 sm:grid-cols-2">
      <UFormField label="Max uploads" description="Total uploads allowed" required>
        <UInput v-model.number="state.max_uploads" type="number" min="1" required class="w-full" />
      </UFormField>

      <UFormField label="Max file size" description="e.g. 100M, 1G, 500MB, 2GB" required>
        <UInput v-model="state.max_size" required placeholder="1G" class="w-full" />
      </UFormField>
    </div>

    <UFormField label="Expiry date & time"
      :description="mode === 'create' ? 'Leave blank to use server default' : 'Update expiry time'">
      <UInput v-model="state.expiry" type="datetime-local" class="w-full" />
    </UFormField>

    <UFormField label="Allowed MIME types" description="One per line. Leave blank for any. Use patterns like video/*">
      <UTextarea v-model="state.allowed_mime" :rows="4" placeholder="video/*&#x0A;image/png&#x0A;application/pdf"
        class="w-full" />
    </UFormField>

    <UCheckbox v-if="mode === 'edit'" v-model="state.disabled" label="Disable this token" />

    <div class="flex items-center justify-end gap-3 pt-2">
      <UButton type="submit" color="primary" :loading="loading">
        {{ submitLabel || (mode === 'edit' ? 'Save changes' : 'Create token') }}
      </UButton>
    </div>
  </form>
</template>

<script setup lang="ts">
import { reactive, watch } from "vue";

type TokenFormPayload = {
  max_uploads: number | null;
  max_size_bytes: number | null;
  expiry_datetime?: string | null;
  extend_hours?: number | null;
  allowed_mime: string[] | null;
  disabled?: boolean;
};

const props = withDefaults(defineProps<{
  mode?: "create" | "edit";
  token?: {
    max_uploads?: number;
    max_size_bytes?: number;
    expires_at?: string;
    allowed_mime?: string[] | null;
    disabled?: boolean;
  } | null;
  submitLabel?: string;
  loading?: boolean;
}>(), {
  mode: "create",
  token: null,
  submitLabel: undefined,
  loading: false,
});

const emit = defineEmits<{
  submit: [payload: TokenFormPayload];
}>();

function formatBytes(bytes: number): string {
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)}G`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)}M`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)}K`;
  return `${bytes}`;
}

function toLocalInput(dateStr: string): string {
  const d = new Date(dateStr);
  const iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString();
  return iso.slice(0, 16);
}

const state = reactive({
  max_uploads: props.token?.max_uploads ?? 1,
  max_size: props.token?.max_size_bytes ? formatBytes(props.token.max_size_bytes) : "1G",
  expiry: props.token?.expires_at ? toLocalInput(props.token.expires_at) : "",
  allowed_mime: (props.token?.allowed_mime || []).join("\n"),
  disabled: props.token?.disabled ?? false,
});

watch(() => props.token, (next) => {
  if (!next) return;
  state.max_uploads = next.max_uploads ?? state.max_uploads;
  state.max_size = next.max_size_bytes ? formatBytes(next.max_size_bytes) : state.max_size;
  state.expiry = next.expires_at ? toLocalInput(next.expires_at) : "";
  state.allowed_mime = (next.allowed_mime || []).join("\n");
  state.disabled = next.disabled ?? false;
});

function normalizeMime(input: string): string[] | null {
  const parts = input.split("\n").map((p) => p.trim()).filter(Boolean);
  return parts.length ? parts : null;
}

function parseSize(input: string): number | null {
  const trimmed = input.trim().toUpperCase();
  const match = trimmed.match(/^([0-9.]+)\s*([KMGT]?)B?$/);
  if (!match || !match[1]) return null;

  const num = parseFloat(match[1]);
  const unit = match[2] || '';

  const multipliers: Record<string, number> = {
    '': 1,
    'K': 1024,
    'M': 1048576,
    'G': 1073741824,
    'T': 1099511627776,
  };

  const multiplier = multipliers[unit];
  if (multiplier === undefined) return null;

  return Math.round(num * multiplier);
}

function handleSubmit() {
  const payload: TokenFormPayload = {
    max_uploads: state.max_uploads || null,
    max_size_bytes: parseSize(state.max_size),
    allowed_mime: normalizeMime(state.allowed_mime),
  };

  if (state.expiry) {
    const localDate = new Date(state.expiry);
    const tzOffset = -localDate.getTimezoneOffset();
    const offsetHours = Math.floor(Math.abs(tzOffset) / 60).toString().padStart(2, '0');
    const offsetMins = (Math.abs(tzOffset) % 60).toString().padStart(2, '0');
    const offsetSign = tzOffset >= 0 ? '+' : '-';
    const isoWithTz = `${state.expiry}:00${offsetSign}${offsetHours}:${offsetMins}`;
    payload.expiry_datetime = isoWithTz;
  }

  if (props.mode === "edit") {
    payload.disabled = state.disabled;
  }

  emit("submit", payload);
}
</script>
