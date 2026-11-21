<template>
  <UApp>
    <div class="fbc-shell-surface flex min-h-dvh flex-col">
      <NuxtLoadingIndicator />
      <header class="border-b border-default bg-default/35 backdrop-blur-md">
        <UContainer class="flex min-h-15 items-center justify-between gap-2 py-2">
          <NuxtLink
            to="/"
            class="flex min-w-0 items-center gap-2.5 rounded-md text-sm font-semibold text-highlighted hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <span
              class="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-default bg-elevated/80"
            >
              <img src="/images/favicon.png" alt="" class="size-6 object-contain" />
            </span>
            <span class="truncate">FBC Uploader</span>
          </NuxtLink>
          <div class="flex shrink-0 items-center gap-0.5 sm:gap-2">
            <template v-if="adminToken">
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                aria-label="Admin dashboard"
                title="Admin dashboard"
                to="/admin"
                icon="i-lucide-layout-dashboard"
              >
                <span class="hidden sm:inline">Dashboard</span>
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                icon="i-lucide-log-out"
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
              <span class="hidden sm:inline">{{ colorModeButtonLabel }}</span>
            </UButton>
          </div>
        </UContainer>
      </header>

      <main class="min-w-0 flex-1">
        <NuxtPage />
      </main>

      <footer v-if="version" class="border-t border-default bg-default/25">
        <UContainer class="flex items-center py-2">
          <UPopover :ui="{ content: 'p-3' }">
            <UButton
              color="neutral"
              variant="ghost"
              icon="i-lucide-info"
              :aria-label="`Build information for ${version.version}`"
              :label="version.version"
            />
            <template #content>
              <div class="min-w-48 max-w-xs space-y-2 text-sm">
                <div class="font-semibold text-highlighted">Build Information</div>
                <div class="space-y-1.5">
                  <div class="grid grid-cols-[auto_1fr] gap-2">
                    <span class="text-muted font-medium">Commit:</span>
                    <span>{{ version.commit_hash }}</span>
                  </div>
                  <div class="grid grid-cols-[auto_1fr] gap-2">
                    <span class="text-muted font-medium">Branch:</span>
                    <span class="wrap-anywhere">{{ version.branch }}</span>
                  </div>
                  <div class="grid grid-cols-[auto_1fr] gap-2">
                    <span class="text-muted font-medium">Built:</span>
                    <span>{{ version.build_date }}</span>
                  </div>
                </div>
              </div>
            </template>
          </UPopover>
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
const { data: version } = useFetch('/api/version', {
  transform: (info: {
    version: string;
    commit_sha: string;
    build_date: string;
    branch: string;
  }) => ({
    version: info.version,
    commit_hash: info.commit_sha.substring(0, 7),
    build_date: info.build_date,
    branch: info.branch,
  }),
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
      return 'i-lucide-sun';
    case 'dark':
      return 'i-lucide-moon';
    default:
      return 'i-lucide-monitor';
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

const colorModeButtonLabel = computed(() => {
  switch (colorModePreference.value) {
    case 'light':
      return 'Light';
    case 'dark':
      return 'Dark';
    default:
      return 'System';
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
    icon: 'i-lucide-log-out',
  });
  await navigateTo('/');
};
</script>
