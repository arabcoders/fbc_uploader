<template>
  <UApp>
    <div class="min-h-screen">
      <header class="backdrop-blur">
        <UContainer class="flex items-center justify-between py-4">
          <NuxtLink to="/" class="flex items-center gap-3 text-lg font-semibold hover:text-primary-300">
            <UIcon name="i-heroicons-home-20-solid" class="h-6 w-6" />
            <span>FBC Uploader</span>
          </NuxtLink>
          <div class="flex items-center gap-3">
            <template v-if="adminToken">
              <UButton color="neutral" variant="ghost" size="sm" @click="navigateTo('/admin')"
                icon="i-heroicons-shield-check-20-solid">
                Dashboard
              </UButton>
              <UButton color="neutral" variant="ghost" size="sm" icon="i-heroicons-arrow-left-on-rectangle-20-solid"
                @click="signOut">
                Sign out
              </UButton>
            </template>
            <UColorModeButton variant="ghost" size="sm" />
          </div>
        </UContainer>
      </header>

      <main class="pb-12">
        <NuxtLoadingIndicator />
        <NuxtPage />
      </main>
    </div>
  </UApp>
</template>

<script setup lang="ts">
const adminToken = useState<string | null>("adminToken", () => null);
const toast = useToast();

const signOut = async () => {
  adminToken.value = null;
  localStorage.removeItem("adminToken");
  toast.add({ title: "Signed out", color: "neutral", icon: "i-heroicons-arrow-left-on-rectangle-20-solid" });
  await navigateTo("/");
}
</script>
