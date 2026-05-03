import { afterEach, describe, expect, it, mock } from 'bun:test';
import { ref } from 'vue';

function dispatchKey(key: string) {
  document.body.dispatchEvent(new window.KeyboardEvent('keydown', { key, bubbles: true }));
}

describe('useSharePlayerShortcuts', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('handles basic playback shortcuts', async () => {
    const { useSharePlayerShortcuts } = await import('~/composables/useSharePlayerShortcuts');
    const media = document.createElement('video');
    let paused = true;

    Object.defineProperty(media, 'paused', {
      configurable: true,
      get: () => paused,
    });
    media.play = mock(async () => {
      paused = false;
    }) as typeof media.play;
    media.pause = mock(() => {
      paused = true;
    }) as typeof media.pause;
    Object.defineProperty(media, 'duration', {
      configurable: true,
      value: 120,
    });
    media.currentTime = 30;
    media.volume = 0.5;

    useSharePlayerShortcuts({
      enabled: ref(true),
      mediaElement: ref(media),
      videoElement: ref(media),
      canToggleSubtitles: ref(false),
      toggleSubtitles: mock(() => {}),
      toggleFullscreen: mock(async () => {}),
    });

    dispatchKey('k');
    expect(media.play).toHaveBeenCalledTimes(1);

    dispatchKey('j');
    expect(media.currentTime).toBe(20);

    dispatchKey('ArrowUp');
    expect(media.volume).toBeCloseTo(0.6, 5);

    dispatchKey('9');
    expect(media.currentTime).toBe(108);
  });

  it('prevents space from toggling twice on a focused media element', async () => {
    const { useSharePlayerShortcuts } = await import('~/composables/useSharePlayerShortcuts');
    const media = document.createElement('video');
    let paused = false;
    let nativeToggleCount = 0;

    Object.defineProperty(media, 'paused', {
      configurable: true,
      get: () => paused,
    });
    media.play = mock(async () => {
      paused = false;
    }) as typeof media.play;
    media.pause = mock(() => {
      paused = true;
    }) as typeof media.pause;

    document.body.appendChild(media);

    media.addEventListener('keydown', (event) => {
      if (event.key === ' ') {
        nativeToggleCount += 1;
        paused = !paused;
      }
    });

    useSharePlayerShortcuts({
      enabled: ref(true),
      mediaElement: ref(media),
      videoElement: ref(media),
      canToggleSubtitles: ref(false),
      toggleSubtitles: mock(() => {}),
      toggleFullscreen: mock(async () => {}),
    });

    media.dispatchEvent(new window.KeyboardEvent('keydown', { key: ' ', bubbles: true }));

    expect(media.pause).toHaveBeenCalledTimes(1);
    expect(nativeToggleCount).toBe(0);
    expect(paused).toBe(true);
  });

  it('toggles subtitle state and help dialog shortcuts', async () => {
    const { useSharePlayerShortcuts } = await import('~/composables/useSharePlayerShortcuts');
    const video = document.createElement('video');
    const subtitlesTrack = { kind: 'subtitles', mode: 'hidden' as 'hidden' | 'showing' };
    Object.defineProperty(video, 'textTracks', {
      configurable: true,
      value: [subtitlesTrack],
    });
    const toggleSubtitles = mock(() => {});

    const { showShortcutHelp } = useSharePlayerShortcuts({
      enabled: ref(true),
      mediaElement: ref(video),
      videoElement: ref(video),
      canToggleSubtitles: ref(true),
      toggleSubtitles,
      toggleFullscreen: mock(async () => {}),
    });

    dispatchKey('c');
    expect(toggleSubtitles).toHaveBeenCalledTimes(1);
    expect(subtitlesTrack.mode).toEqual('showing');

    dispatchKey('/');
    expect(showShortcutHelp.value).toBe(true);

    dispatchKey('/');
    expect(showShortcutHelp.value).toBe(false);
  });
});
