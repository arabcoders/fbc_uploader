<template>
  <div
    ref="playerContainer"
    class="relative flex w-full overflow-hidden bg-black"
    :class="
      isPlayerFullscreen
        ? 'h-screen w-screen max-h-screen max-w-none items-center justify-center'
        : 'max-h-[70vh] max-w-full items-center justify-center sm:max-h-[72vh]'
    "
  >
    <button
      v-if="!active"
      type="button"
      class="group absolute inset-0 z-40 block overflow-hidden bg-black text-left"
      @click="activatePlayer"
    >
      <img
        v-if="posterUrl"
        :src="posterUrl"
        :alt="`${upload.filename || 'Untitled media'} preview`"
        class="block h-full w-full bg-black object-contain opacity-90 transition duration-200 group-hover:opacity-100"
      />
      <div v-else class="flex h-full w-full items-center justify-center bg-black/90 text-white/80">
        <UIcon name="i-heroicons-film-20-solid" class="size-12" />
      </div>
      <div
        class="pointer-events-none absolute inset-0 bg-linear-to-t from-black/70 via-transparent to-black/20"
      />
      <div
        class="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-4 px-4 py-4 sm:px-6"
      >
        <div class="min-w-0">
          <div class="text-xs uppercase tracking-[0.2em] text-white/70">Click to play</div>
          <div class="mt-1 truncate text-lg font-semibold text-white">
            {{ upload.filename || 'Untitled media' }}
          </div>
        </div>
        <div
          class="flex size-16 shrink-0 items-center justify-center rounded-full bg-white/12 text-white backdrop-blur ring-1 ring-white/25"
        >
          <UIcon name="i-heroicons-play-20-solid" class="ml-1 size-8" />
        </div>
      </div>
    </button>

    <video
      ref="videoElement"
      :key="upload.public_id"
      class="share-video-element block bg-black object-contain"
      :class="
        isPlayerFullscreen
          ? 'h-full w-full max-h-screen max-w-screen'
          : 'h-auto w-full max-w-full max-h-[70vh] sm:max-h-[72vh]'
      "
      playsinline
      webkit-playsinline
      preload="metadata"
      :poster="posterUrl || undefined"
      @error="emit('media-error')"
      @loadeddata="syncCustomVideoState"
      @loadedmetadata="handleVideoLoadedMetadata"
      @timeupdate="handleVideoTimeUpdate"
      @play="handleVideoPlay"
      @pause="handleVideoPause"
      @dblclick="handleVideoDoubleClick"
      @pointermove="showCustomControls"
      @resize="scheduleAssLayoutRefresh"
      @volumechange="handleMediaVolumeChange"
      @webkitbeginfullscreen="handleVideoWebkitBeginFullscreen"
      @webkitendfullscreen="handleVideoWebkitEndFullscreen"
    >
      <source :src="mediaUrl" :type="upload.mimetype || undefined" />
      <track
        v-if="nativeSubtitleTrack && subtitleEnabled"
        :key="nativeSubtitleTrack.url"
        kind="subtitles"
        srclang="und"
        label="Subtitles"
        default
        :src="nativeSubtitleTrack.url"
      />
      Your browser does not support the video tag.
    </video>

    <button
      v-if="active && shouldEnableMobileSeekZones"
      type="button"
      class="absolute inset-y-0 left-0 z-10 w-1/3"
      aria-label="Back 10 seconds"
      @click="seekBy(-10)"
    />
    <button
      v-if="active && isTouchDevice"
      type="button"
      class="absolute inset-y-0 left-1/3 z-10 w-1/3"
      :aria-label="customControlsVisible ? 'Hide controls' : 'Show controls'"
      @click="toggleCustomControlsVisibility"
    />
    <button
      v-if="active && shouldEnableMobileSeekZones"
      type="button"
      class="absolute inset-y-0 right-0 z-10 w-1/3"
      aria-label="Forward 10 seconds"
      @click="seekBy(10)"
    />

    <div
      v-if="usesAssSubtitleTrack"
      ref="assOverlayElement"
      class="pointer-events-none absolute inset-0 z-20 overflow-hidden"
      aria-hidden="true"
    />

    <div
      v-if="active && shouldEnableMobileSeekZones && customControlsVisible"
      class="pointer-events-none absolute inset-y-0 left-0 z-20 flex w-1/3 items-center justify-start px-5"
    >
      <div
        class="rounded-full bg-black/60 px-4 py-2 text-sm font-semibold text-white backdrop-blur-sm"
      >
        -10s
      </div>
    </div>
    <div
      v-if="active && shouldEnableMobileSeekZones && customControlsVisible"
      class="pointer-events-none absolute inset-y-0 right-0 z-20 flex w-1/3 items-center justify-end px-5"
    >
      <div
        class="rounded-full bg-black/60 px-4 py-2 text-sm font-semibold text-white backdrop-blur-sm"
      >
        +10s
      </div>
    </div>

    <div
      v-if="active"
      class="absolute inset-x-0 bottom-0 z-30 bg-linear-to-t from-black/95 via-black/70 to-transparent px-3 pb-3 pt-10 text-white transition-opacity duration-200"
      :class="customControlsVisible ? 'opacity-100' : 'pointer-events-none opacity-0'"
      @click.self="toggleCustomControlsVisibility"
      @pointermove="showCustomControls"
    >
      <div class="rounded-2xl border border-white/10 bg-black/45 p-3 shadow-2xl backdrop-blur-md">
        <div class="space-y-3">
          <input
            :value="customVideoProgress"
            type="range"
            min="0"
            max="1000"
            step="1"
            class="h-1.5 w-full accent-white"
            aria-label="Seek video"
            @input="handleCustomVideoSeek"
          />
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <UButton
                color="neutral"
                variant="soft"
                size="sm"
                :icon="
                  isCustomVideoPaused ? 'i-heroicons-play-20-solid' : 'i-heroicons-pause-20-solid'
                "
                :aria-label="isCustomVideoPaused ? 'Play video' : 'Pause video'"
                @click="toggleCustomVideoPlayback"
              />
              <div class="min-w-0 text-xs font-medium text-white/90">
                {{ customVideoTimeLabel }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <UButton
                color="neutral"
                variant="soft"
                size="sm"
                :icon="
                  effectiveStoredMediaVolume <= 0
                    ? 'i-heroicons-speaker-x-mark-20-solid'
                    : 'i-heroicons-speaker-wave-20-solid'
                "
                :aria-label="effectiveStoredMediaVolume <= 0 ? 'Unmute video' : 'Mute video'"
                @click="toggleCurrentMediaMute"
              />
              <input
                :value="Math.round(effectiveStoredMediaVolume * 100)"
                type="range"
                min="0"
                max="100"
                step="1"
                class="w-20 accent-white"
                aria-label="Video volume"
                @input="handleCustomVideoVolumeChange"
              />
              <UButton
                color="neutral"
                variant="soft"
                size="sm"
                :icon="
                  isPlayerFullscreen
                    ? 'i-heroicons-arrows-pointing-in-20-solid'
                    : 'i-heroicons-arrows-pointing-out-20-solid'
                "
                :aria-label="isPlayerFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
                @click="togglePlayerFullscreen"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { SubtitleTrack } from '~/types/subtitles';
import type { UploadRow } from '~/types/uploads';
import { useSharePlayerShortcuts } from '~/composables/useSharePlayerShortcuts';
import { useShareSubtitles } from '~/composables/useShareSubtitles';
import { useShareMediaVolume } from '~/composables/useShareMediaVolume';
import { useShareShortcutHelp } from '~/composables/useShareShortcutHelp';
import {
  canRequestFullscreen,
  exitDocumentFullscreen,
  getFullscreenElement,
  requestElementFullscreen,
} from '~/utils/fullscreen';

const props = defineProps<{
  upload: UploadRow;
  mediaUrl: string;
  posterUrl: string;
  downloadToken: string;
  active: boolean;
}>();

const emit = defineEmits<{
  activate: [];
  'media-error': [];
  'clear-media-error': [];
  'subtitle-state-change': [
    payload: {
      subtitleLoading: boolean;
      subtitleLoadError: string;
      subtitleEnabled: boolean;
      hasSubtitles: boolean;
      selectedSubtitleTrack: SubtitleTrack | null;
      isFullscreen: boolean;
    },
  ];
}>();

const {
  mediaVolume,
  mediaMuted,
  effectiveStoredMediaVolume,
  setStoredMediaVolume,
  adjustStoredMediaVolume,
  toggleStoredMediaMute,
} = useShareMediaVolume();
const showShortcutHelp = useShareShortcutHelp();

const videoElement = ref<HTMLVideoElement | null>(null);
const playerContainer = ref<HTMLElement | null>(null);
const assOverlayElement = ref<HTMLElement | null>(null);
const isPlayerFullscreen = ref(false);
const assLayoutVersion = ref(0);
const customControlsVisible = ref(true);
const customVideoCurrentTime = ref(0);
const customVideoDuration = ref(0);
const isCustomVideoPaused = ref(true);
const isTouchDevice = ref(false);

let assLayoutRefreshFrame = 0;
let customControlsHideTimeout = 0;
let mediaGainAudioContext: AudioContext | null = null;
let mediaGainSourceNode: MediaElementAudioSourceNode | null = null;
let mediaGainNode: GainNode | null = null;
let mediaGainElement: HTMLMediaElement | null = null;

const isPlaying = computed(() => !isCustomVideoPaused.value);
const customVideoProgress = computed(() => {
  if (!customVideoDuration.value) return 0;
  return Math.round((customVideoCurrentTime.value / customVideoDuration.value) * 1000);
});
const customVideoTimeLabel = computed(() => {
  const currentLabel = formatDuration(Math.round(customVideoCurrentTime.value));
  const durationLabel = customVideoDuration.value
    ? formatDuration(Math.round(customVideoDuration.value))
    : '--:--';
  return `${currentLabel} / ${durationLabel}`;
});
const shouldEnableMobileSeekZones = computed(() => {
  return Boolean(isTouchDevice.value && isPlaying.value);
});
const usesMediaGainVolumeFallback = computed(() => {
  return Boolean(isTouchDevice.value && getAudioContextConstructor());
});

const {
  subtitleLoading,
  subtitleLoadError,
  subtitleEnabled,
  selectedSubtitleTrack,
  nativeSubtitleTrack,
  usesAssSubtitleTrack,
  hasSubtitles,
} = useShareSubtitles({
  downloadToken: computed(() => props.downloadToken),
  selectedUpload: computed(() => props.upload),
  selectedIsVideo: computed(() => true),
  canPlaySelectedMedia: computed(() => true),
  shouldRenderSelectedMedia: computed(() => props.active),
  assLayoutVersion,
  videoElement,
  overlayElement: assOverlayElement,
});

watch(
  [
    subtitleLoading,
    subtitleLoadError,
    subtitleEnabled,
    hasSubtitles,
    selectedSubtitleTrack,
    isPlayerFullscreen,
  ],
  () => {
    emit('subtitle-state-change', {
      subtitleLoading: subtitleLoading.value,
      subtitleLoadError: subtitleLoadError.value,
      subtitleEnabled: subtitleEnabled.value,
      hasSubtitles: hasSubtitles.value,
      selectedSubtitleTrack: selectedSubtitleTrack.value,
      isFullscreen: isPlayerFullscreen.value,
    });
  },
  { immediate: true },
);

watch(
  () => props.active,
  (active) => {
    if (!active) {
      clearCustomControlsHideTimeout();
      customControlsVisible.value = true;
      return;
    }

    showCustomControls();
    syncCustomVideoState();
  },
  { immediate: true },
);

watch(
  [mediaVolume, mediaMuted],
  ([nextVolume]) => {
    const normalizedVolume = normalizeMediaVolume(nextVolume);
    if (normalizedVolume !== nextVolume) {
      mediaVolume.value = normalizedVolume;
      return;
    }

    applyStoredMediaState(videoElement.value);
    syncCustomVideoState();
  },
  { immediate: true },
);

watch(
  videoElement,
  (element, previousElement) => {
    if (previousElement && previousElement !== element) {
      disconnectMediaGainController();
    }

    applyStoredMediaState(element);
    syncCustomVideoState();
  },
  { immediate: true },
);

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
  }

  return [minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function normalizeMediaVolume(volume: number): number {
  if (!Number.isFinite(volume)) return 1;
  return Math.min(1, Math.max(0, volume));
}

function getAudioContextConstructor(): typeof AudioContext | null {
  if (!import.meta.client) return null;

  const maybeWindow = window as Window &
    typeof globalThis & {
      webkitAudioContext?: typeof AudioContext;
    };
  return maybeWindow.AudioContext || maybeWindow.webkitAudioContext || null;
}

function emitClearMediaError() {
  emit('clear-media-error');
}

function activatePlayer() {
  emit('activate');
}

function handleVideoLoadedMetadata() {
  emitClearMediaError();
  syncCustomVideoState();
  showCustomControls();
  scheduleAssLayoutRefresh();
}

function handleVideoTimeUpdate() {
  syncCustomVideoState();
}

function handleVideoPlay() {
  emitClearMediaError();
  void resumeMediaGainController();
  syncCustomVideoState();
  showCustomControls();
}

function handleVideoPause() {
  syncCustomVideoState();
  clearCustomControlsHideTimeout();
  customControlsVisible.value = true;
}

function handleVideoDoubleClick() {
  void togglePlayerFullscreen();
}

function handleVideoWebkitBeginFullscreen() {
  scheduleAssLayoutRefresh();
}

function handleVideoWebkitEndFullscreen() {
  scheduleAssLayoutRefresh();
}

function handleMediaVolumeChange(event: Event) {
  const target = event.target as HTMLMediaElement | null;
  if (!target || typeof target.volume !== 'number') return;

  if (target.muted !== mediaMuted.value) {
    mediaMuted.value = target.muted;
  }

  if (!usesMediaGainVolumeFallback.value) {
    const normalizedVolume = normalizeMediaVolume(target.volume);
    if (Math.abs(mediaVolume.value - normalizedVolume) > 0.001) {
      mediaVolume.value = normalizedVolume;
    }
  }

  syncCustomVideoState();
}

function handleCustomVideoSeek(event: Event) {
  const target = event.target as HTMLInputElement | null;
  if (!target || !videoElement.value || !customVideoDuration.value) return;

  const sliderValue = Number(target.value);
  if (!Number.isFinite(sliderValue)) return;

  videoElement.value.currentTime = (sliderValue / 1000) * customVideoDuration.value;
  syncCustomVideoState();
  showCustomControls();
}

function handleCustomVideoVolumeChange(event: Event) {
  const target = event.target as HTMLInputElement | null;
  if (!target || !videoElement.value) return;

  setStoredMediaVolume(Number(target.value) / 100);
  applyStoredMediaState(videoElement.value);
  syncCustomVideoState();
  showCustomControls();
  void resumeMediaGainController();
}

async function toggleCustomVideoPlayback() {
  if (!videoElement.value) return;

  try {
    if (videoElement.value.paused) {
      await resumeMediaGainController();
      await videoElement.value.play();
      syncCustomVideoState();
      showCustomControls();
      return;
    }

    videoElement.value.pause();
    syncCustomVideoState();
  } catch {}
}

function toggleCurrentMediaMute() {
  toggleStoredMediaMute();
  applyStoredMediaState(videoElement.value);
  syncCustomVideoState();
  showCustomControls();
  void resumeMediaGainController();
}

function seekBy(deltaSeconds: number) {
  if (!videoElement.value) return;

  if (!isPlaying.value) {
    showCustomControls();
    return;
  }

  const duration = Number.isFinite(videoElement.value.duration) ? videoElement.value.duration : 0;
  const nextTime = Math.min(
    Math.max(videoElement.value.currentTime + deltaSeconds, 0),
    duration || Infinity,
  );
  videoElement.value.currentTime = nextTime;
  syncCustomVideoState();
  showCustomControls();
}

function applyStoredMediaState(element: HTMLMediaElement | null) {
  if (!element) return;

  if (usesMediaGainVolumeFallback.value) {
    ensureMediaGainController(element);
    if (element.muted !== mediaMuted.value) {
      element.muted = mediaMuted.value;
    }
    if (mediaGainNode) {
      mediaGainNode.gain.value = effectiveStoredMediaVolume.value;
    }
    return;
  }

  const normalizedVolume = normalizeMediaVolume(mediaVolume.value);
  if (Math.abs(element.volume - normalizedVolume) > 0.001) {
    element.volume = normalizedVolume;
  }

  if (element.muted !== mediaMuted.value) {
    element.muted = mediaMuted.value;
  }
}

function ensureMediaGainController(element: HTMLMediaElement | null) {
  if (!usesMediaGainVolumeFallback.value || !element) return;

  if (mediaGainElement === element && mediaGainNode) {
    mediaGainNode.gain.value = effectiveStoredMediaVolume.value;
    return;
  }

  disconnectMediaGainController();

  const AudioContextConstructor = getAudioContextConstructor();
  if (!AudioContextConstructor) return;

  if (!mediaGainAudioContext || mediaGainAudioContext.state === 'closed') {
    try {
      mediaGainAudioContext = new AudioContextConstructor();
    } catch {
      mediaGainAudioContext = null;
      return;
    }
  }

  try {
    mediaGainSourceNode = mediaGainAudioContext.createMediaElementSource(element);
    mediaGainNode = mediaGainAudioContext.createGain();
    mediaGainSourceNode.connect(mediaGainNode);
    mediaGainNode.connect(mediaGainAudioContext.destination);
    mediaGainNode.gain.value = effectiveStoredMediaVolume.value;
    mediaGainElement = element;
  } catch {
    disconnectMediaGainController();
  }
}

async function resumeMediaGainController() {
  if (!usesMediaGainVolumeFallback.value) return;

  ensureMediaGainController(videoElement.value);
  if (!mediaGainAudioContext || mediaGainAudioContext.state !== 'suspended') return;

  try {
    await mediaGainAudioContext.resume();
  } catch {}
}

function disconnectMediaGainController() {
  try {
    mediaGainSourceNode?.disconnect();
  } catch {}

  try {
    mediaGainNode?.disconnect();
  } catch {}

  mediaGainSourceNode = null;
  mediaGainNode = null;
  mediaGainElement = null;
}

function syncCustomVideoState() {
  const video = videoElement.value;
  if (!video) {
    customVideoCurrentTime.value = 0;
    customVideoDuration.value = 0;
    isCustomVideoPaused.value = true;
    return;
  }

  const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
  const currentTime =
    Number.isFinite(video.currentTime) && video.currentTime > 0 ? video.currentTime : 0;

  customVideoDuration.value = duration;
  customVideoCurrentTime.value = currentTime;
  isCustomVideoPaused.value = video.paused;
}

function scheduleAssLayoutRefresh() {
  if (!usesAssSubtitleTrack.value) return;

  if (assLayoutRefreshFrame) {
    window.cancelAnimationFrame(assLayoutRefreshFrame);
  }

  void nextTick(() => {
    assLayoutRefreshFrame = window.requestAnimationFrame(() => {
      assLayoutRefreshFrame = 0;
      assLayoutVersion.value += 1;
    });
  });
}

function showCustomControls() {
  customControlsVisible.value = true;
  clearCustomControlsHideTimeout();

  if (videoElement.value?.paused) {
    return;
  }

  customControlsHideTimeout = window.setTimeout(() => {
    customControlsVisible.value = false;
  }, 2500);
}

function toggleCustomControlsVisibility() {
  if (!customControlsVisible.value) {
    showCustomControls();
    return;
  }

  if (videoElement.value?.paused) {
    return;
  }

  clearCustomControlsHideTimeout();
  customControlsVisible.value = false;
}

function clearCustomControlsHideTimeout() {
  if (customControlsHideTimeout) {
    window.clearTimeout(customControlsHideTimeout);
    customControlsHideTimeout = 0;
  }
}

function syncPlayerFullscreenState() {
  const fullscreenElement = getFullscreenElement();
  isPlayerFullscreen.value = Boolean(
    fullscreenElement && playerContainer.value && fullscreenElement === playerContainer.value,
  );
  scheduleAssLayoutRefresh();
}

async function togglePlayerFullscreen() {
  if (!playerContainer.value || !canRequestFullscreen(playerContainer.value)) return;

  try {
    if (isPlayerFullscreen.value) {
      await exitDocumentFullscreen();
    } else {
      await requestElementFullscreen(playerContainer.value);
    }
  } catch {}
}

useSharePlayerShortcuts({
  enabled: computed(() => props.active && Boolean(videoElement.value)),
  mediaElement: videoElement,
  videoElement,
  adjustVolume: (delta) => {
    adjustStoredMediaVolume(delta);
    applyStoredMediaState(videoElement.value);
    syncCustomVideoState();
    showCustomControls();
    void resumeMediaGainController();
  },
  canToggleSubtitles: hasSubtitles,
  shortcutHelpOpen: showShortcutHelp,
  toggleSubtitles: () => {
    subtitleEnabled.value = !subtitleEnabled.value;
  },
  toggleFullscreen: togglePlayerFullscreen,
  toggleMute: toggleCurrentMediaMute,
});

defineExpose({
  async play() {
    applyStoredMediaState(videoElement.value);
    await resumeMediaGainController();
    await videoElement.value?.play();
  },
  async toggleFullscreen() {
    await togglePlayerFullscreen();
  },
  setSubtitleEnabled(enabled: boolean) {
    subtitleEnabled.value = enabled;
  },
});

onMounted(() => {
  isTouchDevice.value = window.matchMedia('(pointer: coarse)').matches;
  document.addEventListener('fullscreenchange', syncPlayerFullscreenState);
  document.addEventListener('webkitfullscreenchange', syncPlayerFullscreenState as EventListener);
  window.addEventListener('resize', scheduleAssLayoutRefresh);
  window.addEventListener('orientationchange', scheduleAssLayoutRefresh);
  syncPlayerFullscreenState();
});

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncPlayerFullscreenState);
  document.removeEventListener(
    'webkitfullscreenchange',
    syncPlayerFullscreenState as EventListener,
  );
  window.removeEventListener('resize', scheduleAssLayoutRefresh);
  window.removeEventListener('orientationchange', scheduleAssLayoutRefresh);

  if (assLayoutRefreshFrame) {
    window.cancelAnimationFrame(assLayoutRefreshFrame);
  }

  clearCustomControlsHideTimeout();
  disconnectMediaGainController();
  if (mediaGainAudioContext && mediaGainAudioContext.state !== 'closed') {
    void mediaGainAudioContext.close().catch(() => {});
  }
  mediaGainAudioContext = null;
});
</script>

<style scoped>
.share-video-element::-webkit-media-controls {
  display: none;
}

.share-video-element::-webkit-media-controls-fullscreen-button {
  display: none;
}
</style>
