import { describe, expect, it, mock } from 'bun:test';
import {
  canRequestFullscreen,
  exitDocumentFullscreen,
  getFullscreenElement,
  requestElementFullscreen,
} from '~/utils/fullscreen';

describe('fullscreen helpers', () => {
  it('detects fullscreen support from the standard API', () => {
    const element = document.createElement('div') as HTMLDivElement & {
      requestFullscreen: () => Promise<void>;
    };
    element.requestFullscreen = mock(async () => {});

    expect(canRequestFullscreen(element)).toBe(true);
  });

  it('uses webkit fullscreen fallbacks when needed', async () => {
    const element = document.createElement('div') as HTMLDivElement & {
      webkitRequestFullscreen?: () => Promise<void>;
    };
    const requestFullscreenMock = mock(async () => {});
    element.webkitRequestFullscreen = requestFullscreenMock;

    await requestElementFullscreen(element);

    expect(requestFullscreenMock).toHaveBeenCalledTimes(1);
  });

  it('prefers browser fullscreen state from the document', () => {
    const fullscreenTarget = document.createElement('div');
    const fullscreenDocument = document as Document & { webkitFullscreenElement?: Element | null };
    Object.defineProperty(fullscreenDocument, 'webkitFullscreenElement', {
      configurable: true,
      value: fullscreenTarget,
    });

    expect(getFullscreenElement(document)).toBe(fullscreenTarget);

    Object.defineProperty(fullscreenDocument, 'webkitFullscreenElement', {
      configurable: true,
      value: null,
    });
  });

  it('falls back to webkit exit fullscreen', async () => {
    const exitFullscreenMock = mock(async () => {});
    const fullscreenDocument = document as Document & {
      exitFullscreen?: () => Promise<void>;
      webkitExitFullscreen?: () => Promise<void>;
    };

    Object.defineProperty(fullscreenDocument, 'exitFullscreen', {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(fullscreenDocument, 'webkitExitFullscreen', {
      configurable: true,
      value: exitFullscreenMock,
    });

    await exitDocumentFullscreen(document);

    expect(exitFullscreenMock).toHaveBeenCalledTimes(1);
  });
});
