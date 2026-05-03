export function shouldHandleKeyboardShortcut(event: KeyboardEvent): boolean {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return true;
  }

  const tagName = target?.tagName?.toLowerCase();
  if (
    tagName === 'input' ||
    tagName === 'textarea' ||
    target?.isContentEditable ||
    target?.getAttribute('contenteditable') === 'true'
  ) {
    return false;
  }

  return true;
}

export function hasModifierKey(event: KeyboardEvent): boolean {
  return event.ctrlKey || event.metaKey || event.altKey;
}

export function clampMediaTime(media: HTMLMediaElement, nextTime: number): void {
  const duration = Number.isFinite(media.duration) ? media.duration : 0;
  media.currentTime = Math.min(
    Math.max(0, nextTime),
    duration > 0 ? duration : Math.max(0, nextTime),
  );
}

export function clampMediaVolume(volume: number): number {
  return Math.min(1, Math.max(0, volume));
}
