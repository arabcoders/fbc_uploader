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

      <footer class="border-t border-gray-200 dark:border-gray-800 mt-auto" v-if="version.loaded">
        <UContainer class="py-6">
          <div class="flex items-center justify-start gap-2 text-sm text-gray-500 dark:text-gray-400">
            <UPopover mode="hover" :ui="{ content: 'p-3' }">
              <span class="cursor-help underline decoration-dotted">{{ version.version }}</span>
              <template #content>
                <div class="space-y-2 text-sm min-w-48">
                  <div class="font-semibold text-highlighted">Build Information</div>
                  <div class="space-y-1.5">
                    <div class="grid grid-cols-[auto_1fr] gap-2">
                      <span class="text-muted font-medium">Commit:</span>
                      <span>{{ version.commit_hash }}</span>
                    </div>
                    <div class="grid grid-cols-[auto_1fr] gap-2">
                      <span class="text-muted font-medium">Branch:</span>
                      <span>{{ version.branch }}</span>
                    </div>
                    <div class="grid grid-cols-[auto_1fr] gap-2">
                      <span class="text-muted font-medium">Built:</span>
                      <span>{{ version.build_date }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </UPopover>
          </div>
        </UContainer>
      </footer>
    </div>
  </UApp>
</template>

<script setup lang="ts">
const adminToken = useState<string | null>("adminToken", () => null);
const toast = useToast();
const version = ref<{
  loaded: boolean;
  version: string;
  commit_hash: string;
  build_date: string;
  branch: string;
}>({
  loaded: false,
  version: "unknown",
  commit_hash: "unknown",
  build_date: "unknown",
  branch: "unknown",
});

const signOut = async () => {
  adminToken.value = null;
  localStorage.removeItem("adminToken");
  toast.add({ title: "Signed out", color: "neutral", icon: "i-heroicons-arrow-left-on-rectangle-20-solid" });
  await navigateTo("/");
}

onMounted(async () => {
  const v_info = await $fetch<{
    version: string;
    commit_sha: string;
    build_date: string;
    branch: string;
  }>('/api/version')

  if (v_info) {
    version.value = {
      loaded: true,
      version: v_info.version,
      commit_hash: v_info.commit_sha.substring(0, 7),
      build_date: v_info.build_date,
      branch: v_info.branch,
    }
  }
});
</script>
