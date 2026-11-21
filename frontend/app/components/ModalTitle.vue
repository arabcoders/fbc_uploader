<template>
  <span class="inline-flex min-w-0 items-start gap-2">
    <UIcon
      :name="icon"
      :class="danger ? 'text-error' : 'text-primary'"
      class="mt-0.5 size-4 shrink-0"
      aria-hidden="true"
    />
    <span class="min-w-0 wrap-anywhere">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  icon: string;
  label: string;
  danger?: boolean;
}>();
</script>
