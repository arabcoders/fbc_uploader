import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test';
import { reactive } from 'vue';
import { useUploadPolling } from '../composables/useUploadPolling';

const originalSetInterval = globalThis.setInterval;
const originalClearInterval = globalThis.clearInterval;

const testGlobals = globalThis as any;

function makeSlot() {
  return reactive({
    file: null,
    values: {},
    error: '',
    working: false,
    progress: 0,
    status: 'postprocessing',
    errors: [],
    paused: false,
    initiated: true,
    uploadId: 'upload-1',
  });
}

describe('useUploadPolling', () => {
  let callbacks: Array<() => void | Promise<void>>;
  let apiFetchMock: ReturnType<typeof mock>;
  let clearIntervalMock: ReturnType<typeof mock>;

  beforeEach(() => {
    callbacks = [];
    apiFetchMock = mock(async () => ({ uploads: [] }));
    clearIntervalMock = mock(() => {});

    testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });

    globalThis.setInterval = ((callback: any) => {
      callbacks.push(callback);
      return callbacks.length as any;
    }) as typeof setInterval;

    globalThis.clearInterval = clearIntervalMock as typeof clearInterval;
  });

  afterEach(() => {
    globalThis.setInterval = originalSetInterval;
    globalThis.clearInterval = originalClearInterval;
    delete testGlobals.useNuxtApp;
  });

  it('marks a slot completed and invokes onComplete when polling finds a completed upload', async () => {
    const { pollUploadStatus } = useUploadPolling();
    const slot = makeSlot();
    const onComplete = mock(() => {});

    apiFetchMock.mockImplementation(async () => ({
      uploads: [{ public_id: 'upload-1', status: 'completed' }],
    }));

    await pollUploadStatus('upload-1', 'token-1', slot, onComplete);

    expect(callbacks).toHaveLength(1);
    await callbacks[0]!();

    expect(apiFetchMock).toHaveBeenCalledWith('/api/tokens/token-1');
    expect(slot.status).toBe('completed');
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(clearIntervalMock).toHaveBeenCalledTimes(1);
  });

  it('marks a slot errored and stores backend error details when polling finds a failed upload', async () => {
    const { pollUploadStatus } = useUploadPolling();
    const slot = makeSlot();

    apiFetchMock.mockImplementation(async () => ({
      uploads: [{ public_id: 'upload-1', status: 'failed', meta_data: { error: 'ffmpeg failed' } }],
    }));

    await pollUploadStatus('upload-1', 'token-1', slot);

    expect(callbacks).toHaveLength(1);
    await callbacks[0]!();

    expect(slot.status).toBe('error');
    expect(slot.error).toBe('ffmpeg failed');
    expect(clearIntervalMock).toHaveBeenCalledTimes(1);
  });

  it('does not create duplicate polling intervals for the same upload', async () => {
    const { pollUploadStatus } = useUploadPolling();
    const slot = makeSlot();

    await pollUploadStatus('upload-1', 'token-1', slot);
    await pollUploadStatus('upload-1', 'token-1', slot);

    expect(callbacks).toHaveLength(1);
  });
});
