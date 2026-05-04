<template>
  <UApp>
    <div class="min-h-screen">
      <header class="backdrop-blur">
        <UContainer class="flex items-center justify-between py-4">
          <NuxtLink
            to="/"
            class="flex items-center gap-3 text-lg font-semibold hover:text-primary-300"
          >
            <UIcon name="i-heroicons-home-20-solid" class="h-6 w-6" />
            <span>FBC Uploader</span>
          </NuxtLink>
          <div class="flex items-center gap-3">
            <template v-if="adminToken">
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                aria-label="Dashboard"
                title="Dashboard"
                @click="navigateTo('/admin')"
                icon="i-heroicons-shield-check-20-solid"
              >
                <span class="hidden sm:inline">Dashboard</span>
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                icon="i-heroicons-arrow-left-on-rectangle-20-solid"
                aria-label="Sign out"
                title="Sign out"
                @click="signOut"
              >
                <span class="hidden sm:inline">Sign out</span>
              </UButton>
            </template>
            <UButton
              size="sm"
              :icon="colorModeButtonIcon"
              :aria-label="colorModeButtonAriaLabel"
              :title="colorModeButtonTitle"
              @click="cycleColorMode"
              color="neutral"
              variant="ghost"
            >
              <span class="hidden sm:inline">Theme</span>
            </UButton>
          </div>
        </UContainer>
      </header>

      <main class="pb-12">
        <NuxtLoadingIndicator />
        <NuxtPage />
      </main>

      <footer class="border-t border-gray-200 dark:border-gray-800 mt-auto" v-if="version.loaded">
        <UContainer class="py-6">
          <div
            class="flex items-center justify-start gap-2 text-sm text-gray-500 dark:text-gray-400"
          >
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
type ColorModePreference = 'system' | 'light' | 'dark';

const colorMode = useColorMode();
const adminToken = useState<string | null>('adminToken', () => null);
const toast = useToast();
const colorModePreferences: Array<ColorModePreference> = ['system', 'light', 'dark'];
const version = ref<{
  loaded: boolean;
  version: string;
  commit_hash: string;
  build_date: string;
  branch: string;
}>({
  loaded: false,
  version: 'unknown',
  commit_hash: 'unknown',
  build_date: 'unknown',
  branch: 'unknown',
});

const colorModePreference = computed<ColorModePreference>(() => {
  const preference = colorMode.preference;
  return colorModePreferences.includes(preference as ColorModePreference)
    ? (preference as ColorModePreference)
    : 'system';
});

const colorModeButtonIcon = computed(() => {
  switch (colorModePreference.value) {
    case 'light':
      return 'i-heroicons-sun-20-solid';
    case 'dark':
      return 'i-heroicons-moon-20-solid';
    default:
      return 'i-heroicons-computer-desktop-20-solid';
  }
});

const nextColorModePreference = computed<ColorModePreference>(() => {
  const currentIndex = colorModePreferences.indexOf(colorModePreference.value);
  return colorModePreferences[(currentIndex + 1) % colorModePreferences.length] ?? 'system';
});

const colorModeButtonTitle = computed(() => {
  switch (colorModePreference.value) {
    case 'light':
      return 'Theme: Light';
    case 'dark':
      return 'Theme: Dark';
    default:
      return 'Theme: System';
  }
});

const colorModeButtonAriaLabel = computed(() => {
  switch (nextColorModePreference.value) {
    case 'light':
      return 'Switch theme to light';
    case 'dark':
      return 'Switch theme to dark';
    default:
      return 'Switch theme to system';
  }
});

const cycleColorMode = (): void => {
  colorMode.preference = nextColorModePreference.value;
};

const signOut = async () => {
  adminToken.value = null;
  localStorage.removeItem('adminToken');
  toast.add({
    title: 'Signed out',
    color: 'neutral',
    icon: 'i-heroicons-arrow-left-on-rectangle-20-solid',
  });
  await navigateTo('/');
};

onMounted(async () => {
  const v_info = await $fetch<{
    version: string;
    commit_sha: string;
    build_date: string;
    branch: string;
  }>('/api/version');

  if (v_info) {
    version.value = {
      loaded: true,
      version: v_info.version,
      commit_hash: v_info.commit_sha.substring(0, 7),
      build_date: v_info.build_date,
      branch: v_info.branch,
    };
  }
});
</script>
