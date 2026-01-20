<template>
  <UContainer class="py-14">
    <div class="max-w-md mx-auto space-y-8">
      <div class="space-y-2 text-center">
        <h1 class="text-3xl font-bold">Admin sign-in</h1>
        <p class="text-muted">Enter the FBC API key to manage upload tokens.</p>
      </div>

      <UCard variant="outline">
        <form class="space-y-6" @submit.prevent="onSubmit">
          <UFormField label="API Key" help="The key is stored locally in your browser." required size="xl">
            <UInput v-model="adminKey" type="password" autocomplete="off" required class="w-full"
              placeholder="FBC API KEY" icon="i-heroicons-key-20-solid" />
          </UFormField>

          <UAlert v-if="error" color="error" variant="soft" icon="i-heroicons-exclamation-triangle-20-solid"
            :title="error" />

          <div class="flex items-center gap-3">
            <UButton type="submit" color="primary" block icon="i-heroicons-arrow-right-on-rectangle-20-solid"
              :loading="loading">
              Sign in
            </UButton>
          </div>
        </form>
      </UCard>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { ApiError } from "~/types/uploads";

const route = useRoute();
const toast = useToast();
const { $apiFetch } = useNuxtApp();

const adminToken = useState<string | null>("adminToken", () => null);
const adminKey = ref(adminToken.value || "");
const loading = ref(false);
const error = ref("");

const redirectTo = computed(() => {
  const redirect = route.query.redirect as string;
  if (redirect && !redirect.startsWith("/admin")) {
    return "/admin";
  }
  return redirect || "/admin";
});

const onSubmit = async () => {
  error.value = "";
  loading.value = true;
  adminToken.value = adminKey.value.trim();


  try {
    await $apiFetch("/api/admin/validate");
    toast.add({ title: "Signed in", color: "success", icon: "i-heroicons-check-circle-20-solid" });
    await navigateTo(redirectTo.value);
  } catch (err) {
    const apiError = err as ApiError;
    adminToken.value = null;
    error.value = apiError?.data?.detail || apiError?.message || "Invalid api key";
    console.log("Admin sign-in error:", err, error.value);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (adminToken.value) {
    await navigateTo(redirectTo.value);
  }
});
</script>
