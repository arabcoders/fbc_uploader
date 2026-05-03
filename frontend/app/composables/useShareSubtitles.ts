import {
  computed,
  getCurrentScope,
  onScopeDispose,
  ref,
  watch,
  type MaybeRefOrGetter,
  toValue,
} from 'vue';
import type { UploadRow } from '~/types/uploads';
import type { SubtitleManifestResponse, SubtitleTrack } from '~/types/subtitles';

type AssRendererInstance = {
  destroy(): unknown;
  show(): unknown;
};

type AssRendererConstructor = new (
  content: string,
  video: HTMLVideoElement,
  options: { container: HTMLElement; resampling: 'video_height' },
) => AssRendererInstance;

type UseShareSubtitlesOptions = {
  downloadToken: MaybeRefOrGetter<string>;
  selectedUpload: MaybeRefOrGetter<UploadRow | null>;
  selectedIsVideo: MaybeRefOrGetter<boolean>;
  canPlaySelectedMedia: MaybeRefOrGetter<boolean>;
  shouldRenderSelectedMedia: MaybeRefOrGetter<boolean>;
  videoElement: MaybeRefOrGetter<HTMLVideoElement | null>;
  overlayElement: MaybeRefOrGetter<HTMLElement | null>;
  fetchSubtitleText?: (url: string) => Promise<string>;
  loadAssRenderer?: () => Promise<AssRendererConstructor>;
};

async function defaultFetchSubtitleText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('Subtitle fetch failed');
  }

  return response.text();
}

async function defaultLoadAssRenderer(): Promise<AssRendererConstructor> {
  const module = await import('assjs');
  return module.default as AssRendererConstructor;
}

export function useShareSubtitles(options: UseShareSubtitlesOptions) {
  const { $apiFetch } = useNuxtApp();
  const fetchSubtitleText = options.fetchSubtitleText || defaultFetchSubtitleText;
  const loadAssRenderer = options.loadAssRenderer || defaultLoadAssRenderer;
  const subtitleTracks = ref<SubtitleTrack[]>([]);
  const subtitleLoading = ref(false);
  const subtitleLoadError = ref('');
  const subtitleEnabled = ref(true);
  const selectedSubtitleTrack = computed(() => subtitleTracks.value[0] || null);
  const nativeSubtitleTrack = computed(() => {
    const track = selectedSubtitleTrack.value;
    return subtitleEnabled.value && track?.renderer === 'native' ? track : null;
  });
  const usesAssSubtitleTrack = computed(() => selectedSubtitleTrack.value?.renderer === 'assjs');
  const hasSubtitles = computed(() => subtitleTracks.value.length > 0);

  let assRenderer: AssRendererInstance | null = null;
  let subtitleRequestId = 0;
  let assRequestId = 0;

  function destroyAssRenderer() {
    assRenderer?.destroy();
    assRenderer = null;
  }

  async function loadSelectedSubtitles() {
    const selectedUpload = toValue(options.selectedUpload);
    const downloadToken = toValue(options.downloadToken);
    const selectedIsVideo = toValue(options.selectedIsVideo);
    const canPlaySelectedMedia = toValue(options.canPlaySelectedMedia);
    const requestId = ++subtitleRequestId;

    assRequestId += 1;
    destroyAssRenderer();
    subtitleTracks.value = [];
    subtitleLoadError.value = '';

    if (!selectedUpload || !selectedIsVideo || !canPlaySelectedMedia || !downloadToken) {
      subtitleLoading.value = false;
      return;
    }

    subtitleLoading.value = true;

    try {
      const response = await $apiFetch<SubtitleManifestResponse>(
        `/api/tokens/${encodeURIComponent(downloadToken)}/uploads/${encodeURIComponent(selectedUpload.public_id)}/subtitles`,
      );

      if (requestId !== subtitleRequestId) {
        return;
      }

      subtitleTracks.value = response.subtitles || [];
      if (subtitleTracks.value.length > 0) {
        subtitleEnabled.value = true;
      }
    } catch {
      if (requestId !== subtitleRequestId) {
        return;
      }

      subtitleLoadError.value = 'Failed to load subtitles for this video.';
    } finally {
      if (requestId === subtitleRequestId) {
        subtitleLoading.value = false;
      }
    }
  }

  async function syncAssRenderer() {
    const track = selectedSubtitleTrack.value;
    const shouldRenderSelectedMedia = toValue(options.shouldRenderSelectedMedia);
    const videoElement = toValue(options.videoElement);
    const overlayElement = toValue(options.overlayElement);
    const requestId = ++assRequestId;

    destroyAssRenderer();

    if (
      !track ||
      track.renderer !== 'assjs' ||
      !subtitleEnabled.value ||
      !shouldRenderSelectedMedia ||
      !videoElement ||
      !overlayElement
    ) {
      return;
    }

    try {
      const subtitleContent = await fetchSubtitleText(track.url);
      if (requestId !== assRequestId) {
        return;
      }

      const ASS = await loadAssRenderer();
      if (requestId !== assRequestId) {
        return;
      }

      assRenderer = new ASS(subtitleContent, videoElement, {
        container: overlayElement,
        resampling: 'video_height',
      }) as AssRendererInstance;
      assRenderer.show();
      subtitleLoadError.value = '';
    } catch {
      if (requestId === assRequestId) {
        subtitleLoadError.value = 'Failed to render ASS subtitles in the browser.';
      }

      destroyAssRenderer();
    }
  }

  watch(
    () => [
      toValue(options.downloadToken),
      toValue(options.selectedUpload)?.public_id || '',
      toValue(options.selectedIsVideo),
      toValue(options.canPlaySelectedMedia),
    ],
    () => {
      void loadSelectedSubtitles();
    },
    { immediate: true },
  );

  watch(
    () => [
      selectedSubtitleTrack.value?.url || '',
      selectedSubtitleTrack.value?.renderer || '',
      subtitleEnabled.value,
      toValue(options.shouldRenderSelectedMedia),
      toValue(options.videoElement),
      toValue(options.overlayElement),
    ],
    () => {
      void syncAssRenderer();
    },
    { immediate: true },
  );

  if (getCurrentScope()) {
    onScopeDispose(() => {
      assRequestId += 1;
      destroyAssRenderer();
    });
  }

  return {
    subtitleTracks,
    subtitleLoading,
    subtitleLoadError,
    subtitleEnabled,
    selectedSubtitleTrack,
    nativeSubtitleTrack,
    usesAssSubtitleTrack,
    hasSubtitles,
    loadSelectedSubtitles,
  };
}
