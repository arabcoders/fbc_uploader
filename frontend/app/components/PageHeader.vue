<template>
  <header class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
    <div class="flex min-w-0 items-start gap-4">
      <span class="fbc-section-icon hidden size-11 sm:inline-flex" aria-hidden="true">
        <UIcon :name="icon" class="size-5" />
      </span>
      <div class="min-w-0 space-y-1.5">
        <p v-if="section" class="text-xs font-medium text-muted">{{ section }}</p>
        <h1 class="text-2xl font-semibold tracking-tight text-highlighted sm:text-3xl">
          {{ title }}
        </h1>
        <p v-if="description" class="max-w-3xl text-sm text-toned">{{ description }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2 lg:justify-end">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  icon: string;
  section?: string;
  description?: string;
}>();
</script>
