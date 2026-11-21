<template>
  <UCard variant="outline" :ui="{ body: 'p-0 sm:p-0' }">
    <UCollapsible v-model:open="open">
      <UButton
        block
        color="neutral"
        variant="ghost"
        icon="i-lucide-megaphone"
        trailing-icon="i-lucide-chevron-down"
        label="Notice"
        class="group justify-start px-4 py-3 sm:px-5"
        :ui="{ trailingIcon: 'ms-auto transition-transform group-data-[state=open]:rotate-180' }"
      />
      <template #content>
        <Markdown :content="content" class="border-t border-default p-4 sm:p-5" />
      </template>
    </UCollapsible>
  </UCard>
</template>

<script setup lang="ts">
defineProps<{ content: string }>();
const open = defineModel<boolean>('open', { required: true });
</script>
