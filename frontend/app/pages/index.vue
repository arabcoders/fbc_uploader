<template>
  <UContainer class="flex justify-center py-10 sm:py-16">
    <UCard variant="outline" class="w-full max-w-md">
      <template #header>
        <div class="flex items-center gap-3">
          <span class="fbc-section-icon" aria-hidden="true">
            <UIcon name="i-lucide-shield-check" class="size-5" />
          </span>
          <div>
            <h1 class="font-semibold text-highlighted">Admin sign-in</h1>
            <p class="text-sm text-toned">Enter your FBC API key to manage upload tokens.</p>
          </div>
        </div>
      </template>

      <form class="space-y-5" @submit.prevent="onSubmit">
        <UAlert
          v-if="error"
          color="error"
          variant="soft"
          icon="i-lucide-triangle-alert"
          title="Could not sign in"
          :description="error"
        />

        <UFormField
          label="API key"
          name="adminKey"
          help="The key is stored locally in your browser."
          required
        >
          <UInput
            v-model="adminKey"
            type="password"
            autocomplete="off"
            required
            :disabled="loading"
            class="w-full"
            placeholder="FBC API key"
            icon="i-lucide-key-round"
          />
        </UFormField>

        <UButton type="submit" block icon="i-lucide-log-in" :loading="loading" label="Sign in" />
      </form>
    </UCard>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ApiError } from '~/types/uploads';

const route = useRoute();
const toast = useToast();
const { $apiFetch } = useNuxtApp();

const adminToken = useState<string | null>('adminToken', () => null);
const adminKey = ref(adminToken.value || '');
const loading = ref(false);
const error = ref('');

const redirectTo = computed(() => {
  const redirect = route.query.redirect as string;
  if (redirect && !redirect.startsWith('/admin')) {
    return '/admin';
  }
  return redirect || '/admin';
});

const onSubmit = async () => {
  error.value = '';
  loading.value = true;
  adminToken.value = adminKey.value.trim();

  try {
    await $apiFetch('/api/admin/validate');
    toast.add({ title: 'Signed in', color: 'success', icon: 'i-lucide-circle-check' });
    await navigateTo(redirectTo.value);
  } catch (err) {
    const apiError = err as ApiError;
    adminToken.value = null;
    error.value = apiError?.data?.detail || apiError?.message || 'Invalid API key';
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  if (adminToken.value) {
    await navigateTo(redirectTo.value);
  }
});
</script>
