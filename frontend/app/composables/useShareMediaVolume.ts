import { computed } from 'vue';
import { useStorage } from '@vueuse/core';

function normalizeMediaVolume(volume: number): number {
  if (!Number.isFinite(volume)) return 1;
  return Math.min(1, Math.max(0, volume));
}

export function useShareMediaVolume() {
  const mediaVolume = useStorage<number>('share_media_volume', 1);
  const mediaMuted = useStorage<boolean>('share_media_muted', false);
  const effectiveStoredMediaVolume = computed(() => {
    return mediaMuted.value ? 0 : normalizeMediaVolume(mediaVolume.value);
  });

  function setStoredMediaVolume(nextVolume: number) {
    const normalizedVolume = normalizeMediaVolume(nextVolume);
    mediaVolume.value = normalizedVolume;
    mediaMuted.value = normalizedVolume <= 0;
  }

  function adjustStoredMediaVolume(delta: number) {
    setStoredMediaVolume(mediaVolume.value + delta);
  }

  function toggleStoredMediaMute() {
    if (mediaMuted.value || effectiveStoredMediaVolume.value <= 0) {
      mediaVolume.value = mediaVolume.value > 0 ? normalizeMediaVolume(mediaVolume.value) : 1;
      mediaMuted.value = false;
      return;
    }

    mediaMuted.value = true;
  }

  return {
    mediaVolume,
    mediaMuted,
    effectiveStoredMediaVolume,
    setStoredMediaVolume,
    adjustStoredMediaVolume,
    toggleStoredMediaMute,
  };
}
