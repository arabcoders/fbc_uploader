import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test';
import { nextTick, ref } from 'vue';
import type { UploadRow } from '~/types/uploads';

const assShowMock = mock(() => {});
const assDestroyMock = mock(() => {});
const assConstructorMock = mock(() => ({
  show: assShowMock,
  destroy: assDestroyMock,
}));

const testGlobals = globalThis as typeof globalThis & {
  useNuxtApp?: () => { $apiFetch: ReturnType<typeof mock> };
};

function makeUpload(overrides: Partial<UploadRow> = {}): UploadRow {
  return {
    public_id: 'upload-1',
    filename: 'sample.mp4',
    mimetype: 'video/mp4',
    status: 'completed',
    ...overrides,
  };
}

async function flushPromises(times = 3) {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

beforeEach(() => {
  assConstructorMock.mockClear();
  assShowMock.mockClear();
  assDestroyMock.mockClear();
});

afterEach(() => {
  delete testGlobals.useNuxtApp;
});

describe('useShareSubtitles', () => {
  it('loads subtitle manifest and exposes the preferred native track', async () => {
    const apiFetchMock = mock(async () => ({
      subtitles: [
        {
          source_format: 'vtt',
          delivery_format: 'vtt',
          renderer: 'native',
          url: '/subs/sample.vtt',
        },
        {
          source_format: 'ass',
          delivery_format: 'ass',
          renderer: 'assjs',
          url: '/subs/sample.ass',
        },
      ],
    }));
    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    const { useShareSubtitles } = await import('~/composables/useShareSubtitles');
    const selectedUpload = ref<UploadRow | null>(makeUpload());
    const selectedIsVideo = ref(true);
    const canPlaySelectedMedia = ref(true);
    const shouldRenderSelectedMedia = ref(false);
    const videoElement = ref<HTMLVideoElement | null>(document.createElement('video'));
    const overlayElement = ref<HTMLElement | null>(document.createElement('div'));

    const { hasSubtitles, nativeSubtitleTrack, selectedSubtitleTrack, usesAssSubtitleTrack } =
      useShareSubtitles({
        downloadToken: ref('download-token'),
        selectedUpload,
        selectedIsVideo,
        canPlaySelectedMedia,
        shouldRenderSelectedMedia,
        videoElement,
        overlayElement,
      });

    await flushPromises();

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/api/tokens/download-token/uploads/upload-1/subtitles',
    );
    expect(hasSubtitles.value).toBe(true);
    expect(selectedSubtitleTrack.value?.source_format).toBe('vtt');
    expect(selectedSubtitleTrack.value?.delivery_format).toBe('vtt');
    expect(nativeSubtitleTrack.value?.url).toBe('/subs/sample.vtt');
    expect(usesAssSubtitleTrack.value).toBe(false);
  });

  it('creates and destroys an ASS renderer for ASS subtitles when playback becomes active', async () => {
    const apiFetchMock = mock(async () => ({
      subtitles: [
        {
          source_format: 'ass',
          delivery_format: 'ass',
          renderer: 'assjs',
          url: '/subs/sample.ass',
        },
      ],
    }));
    const fetchSubtitleText = mock(async () => '[Script Info]\nTitle: Demo\n');
    const loadAssRenderer = mock(async () => assConstructorMock as any);

    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    const { useShareSubtitles } = await import('~/composables/useShareSubtitles');
    const selectedUpload = ref<UploadRow | null>(makeUpload());
    const selectedIsVideo = ref(true);
    const canPlaySelectedMedia = ref(true);
    const shouldRenderSelectedMedia = ref(false);
    const videoElement = ref<HTMLVideoElement | null>(document.createElement('video'));
    const overlayElement = ref<HTMLElement | null>(document.createElement('div'));

    const { usesAssSubtitleTrack } = useShareSubtitles({
      downloadToken: ref('download-token'),
      selectedUpload,
      selectedIsVideo,
      canPlaySelectedMedia,
      shouldRenderSelectedMedia,
      videoElement,
      overlayElement,
      fetchSubtitleText,
      loadAssRenderer,
    });

    await flushPromises();

    expect(usesAssSubtitleTrack.value).toBe(true);
    expect(assConstructorMock).not.toHaveBeenCalled();

    shouldRenderSelectedMedia.value = true;
    await flushPromises(5);

    expect(fetchSubtitleText).toHaveBeenCalledWith('/subs/sample.ass');
    expect(loadAssRenderer).toHaveBeenCalledTimes(1);
    expect(assConstructorMock).toHaveBeenCalledTimes(1);
    expect(assShowMock).toHaveBeenCalledTimes(1);

    selectedUpload.value = makeUpload({ public_id: 'upload-2', filename: 'second.mp4' });
    await flushPromises();

    expect(assDestroyMock.mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('resyncs ASS subtitles immediately when the renderer is created during active playback', async () => {
    const apiFetchMock = mock(async () => ({
      subtitles: [
        {
          source_format: 'ass',
          delivery_format: 'ass',
          renderer: 'assjs',
          url: '/subs/sample.ass',
        },
      ],
    }));
    const fetchSubtitleText = mock(async () => '[Script Info]\nTitle: Demo\n');
    const loadAssRenderer = mock(
      async () =>
        mock(() => ({
          show: assShowMock,
          destroy: assDestroyMock,
        })) as any,
    );

    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    const { useShareSubtitles } = await import('~/composables/useShareSubtitles');
    const selectedUpload = ref<UploadRow | null>(makeUpload());
    const selectedIsVideo = ref(true);
    const canPlaySelectedMedia = ref(true);
    const shouldRenderSelectedMedia = ref(true);
    const dispatchedEventTypes: string[] = [];
    const dispatchEventMock = mock((event: Event) => {
      dispatchedEventTypes.push(event.type);
      return true;
    });
    const videoElement = ref<HTMLVideoElement | null>({
      paused: false,
      dispatchEvent: dispatchEventMock,
    } as unknown as HTMLVideoElement);
    const overlayElement = ref<HTMLElement | null>(document.createElement('div'));

    useShareSubtitles({
      downloadToken: ref('download-token'),
      selectedUpload,
      selectedIsVideo,
      canPlaySelectedMedia,
      shouldRenderSelectedMedia,
      videoElement,
      overlayElement,
      fetchSubtitleText,
      loadAssRenderer,
    });

    await flushPromises(5);

    expect(dispatchEventMock).toHaveBeenCalledTimes(2);
    expect(dispatchedEventTypes[0]).toBe('seeking');
    expect(dispatchedEventTypes[1]).toBe('playing');
  });

  it('recreates an ASS renderer when the layout version changes without refetching subtitles', async () => {
    const apiFetchMock = mock(async () => ({
      subtitles: [
        {
          source_format: 'ass',
          delivery_format: 'ass',
          renderer: 'assjs',
          url: '/subs/sample.ass',
        },
      ],
    }));
    const fetchSubtitleText = mock(async () => '[Script Info]\nTitle: Demo\n');
    const loadAssRenderer = mock(async () => assConstructorMock as any);

    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    const { useShareSubtitles } = await import('~/composables/useShareSubtitles');
    const selectedUpload = ref<UploadRow | null>(makeUpload());
    const selectedIsVideo = ref(true);
    const canPlaySelectedMedia = ref(true);
    const shouldRenderSelectedMedia = ref(true);
    const assLayoutVersion = ref(0);
    const videoElement = ref<HTMLVideoElement | null>(document.createElement('video'));
    const overlayElement = ref<HTMLElement | null>(document.createElement('div'));

    useShareSubtitles({
      downloadToken: ref('download-token'),
      selectedUpload,
      selectedIsVideo,
      canPlaySelectedMedia,
      shouldRenderSelectedMedia,
      assLayoutVersion,
      videoElement,
      overlayElement,
      fetchSubtitleText,
      loadAssRenderer,
    });

    await flushPromises(5);

    expect(fetchSubtitleText).toHaveBeenCalledTimes(1);
    expect(assConstructorMock).toHaveBeenCalledTimes(1);

    assLayoutVersion.value += 1;
    await flushPromises(5);

    expect(fetchSubtitleText).toHaveBeenCalledTimes(1);
    expect(assDestroyMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    expect(assConstructorMock).toHaveBeenCalledTimes(2);
  });

  it('recreates an ASS renderer across repeated layout refreshes without refetching subtitles', async () => {
    const apiFetchMock = mock(async () => ({
      subtitles: [
        {
          source_format: 'ass',
          delivery_format: 'ass',
          renderer: 'assjs',
          url: '/subs/sample.ass',
        },
      ],
    }));
    const fetchSubtitleText = mock(async () => '[Script Info]\nTitle: Demo\n');
    const loadAssRenderer = mock(async () => assConstructorMock as any);

    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    const { useShareSubtitles } = await import('~/composables/useShareSubtitles');
    const selectedUpload = ref<UploadRow | null>(makeUpload());
    const selectedIsVideo = ref(true);
    const canPlaySelectedMedia = ref(true);
    const shouldRenderSelectedMedia = ref(true);
    const assLayoutVersion = ref(0);
    const videoElement = ref<HTMLVideoElement | null>(document.createElement('video'));
    const overlayElement = ref<HTMLElement | null>(document.createElement('div'));

    useShareSubtitles({
      downloadToken: ref('download-token'),
      selectedUpload,
      selectedIsVideo,
      canPlaySelectedMedia,
      shouldRenderSelectedMedia,
      assLayoutVersion,
      videoElement,
      overlayElement,
      fetchSubtitleText,
      loadAssRenderer,
    });

    await flushPromises(5);

    assLayoutVersion.value += 1;
    await flushPromises(5);
    assLayoutVersion.value += 1;
    await flushPromises(5);

    expect(fetchSubtitleText).toHaveBeenCalledTimes(1);
    expect(assConstructorMock).toHaveBeenCalledTimes(3);
  });
});
