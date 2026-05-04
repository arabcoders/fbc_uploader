import { afterEach, beforeEach, describe, expect, it, mock } from 'bun:test';
import type { Slot } from '~/types/uploads';

function makeFile(size: number, name = 'a.bin', type = 'application/octet-stream'): File {
  return new File([new Uint8Array(size)], name, { type });
}

const makeSlot = (): Slot => ({
  file: null,
  values: {},
  error: '',
  working: false,
  progress: 0,
  status: '',
  errors: [],
  paused: false,
  initiated: false,
  uploadId: 'test-upload-id',
});

type MockUploadConstructor = {
  implementation: ((file: any, opts: any) => any) | null;
  new (file: any, opts: any): any;
};

const MockUpload: MockUploadConstructor = function (this: unknown, file: any, opts: any) {
  if (MockUpload.implementation) {
    return MockUpload.implementation(file, opts);
  }

  return {
    start: () => {},
  };
} as unknown as MockUploadConstructor;

MockUpload.implementation = null;

class MockDefaultRequest {
  headers: Record<string, string> = {};

  constructor(
    private readonly method: string,
    private readonly url: string,
  ) {}

  getMethod() {
    return this.method;
  }

  getURL() {
    return this.url;
  }

  setHeader(header: string, value: string) {
    this.headers[header] = value;
  }

  getHeader(header: string) {
    return this.headers[header];
  }

  setProgressHandler() {}

  async send() {
    return {
      getStatus: () => 204,
      getHeader: () => null,
      getBody: () => '',
      getUnderlyingObject: () => null,
    };
  }

  abort() {
    return Promise.resolve();
  }

  getUnderlyingObject() {
    return null;
  }
}

class MockDefaultHttpStack {
  createRequest(method: string, url: string) {
    return new MockDefaultRequest(method, url);
  }

  getName() {
    return 'MockDefaultHttpStack';
  }
}

mock.module('tus-js-client', () => ({
  Upload: MockUpload,
  DefaultHttpStack: MockDefaultHttpStack,
}));

const testGlobals = globalThis as typeof globalThis & {
  useNuxtApp?: () => { $apiFetch: ReturnType<typeof mock> };
};

let apiFetchMock = mock(async () => ({ status: 'completed' }));

beforeEach(() => {
  MockUpload.implementation = null;
  apiFetchMock = mock(async () => ({ status: 'completed' }));
  testGlobals.useNuxtApp = () => ({ $apiFetch: apiFetchMock });
});

afterEach(() => {
  delete testGlobals.useNuxtApp;
});

describe('useTusUpload', () => {
  it('starts upload and finalizes through the completion endpoint', async () => {
    let uploadOptions: any;

    MockUpload.implementation = (_file: any, opts: any) => ({
      start: () => {
        uploadOptions = opts;
        opts.onProgress(5, 10);
        opts.onSuccess();
      },
    });

    const { useTusUpload } = await import('~/composables/useTusUpload');
    const { startTusUpload } = useTusUpload();
    const slot = makeSlot();
    const file = makeFile(10);

    await startTusUpload(
      slot,
      'http://upload',
      file,
      'token-123',
      { max_chunk_bytes: 50 } as any,
      50,
    );

    expect(slot.status).toBe('completed');
    expect(slot.progress).toBe(100);
    expect(slot.bytesUploaded).toBe(10);
    expect(slot.tusUpload).toBeUndefined();
    expect(uploadOptions.chunkSize).toBe(10);
    expect(uploadOptions.httpStack).toBeDefined();
  });

  it('adds a checksum header to PATCH requests', async () => {
    let uploadOptions: any;
    const originalError = console.error;
    console.error = mock(() => {}) as typeof console.error;

    try {
      MockUpload.implementation = (_file: any, opts: any) => ({
        start: () => {
          uploadOptions = opts;
          opts.onError(new Error('stop'));
        },
      });

      const { useTusUpload } = await import('~/composables/useTusUpload');
      const { startTusUpload } = useTusUpload();
      const slot = makeSlot();
      const file = makeFile(20 * 1024 * 1024);

      await expect(
        startTusUpload(
          slot,
          'http://upload',
          file,
          'token-123',
          { max_chunk_bytes: 90 * 1024 * 1024 } as any,
          90 * 1024 * 1024,
        ),
      ).rejects.toThrow('stop');

      expect(uploadOptions.chunkSize).toBe(20 * 1024 * 1024);

      const request = uploadOptions.httpStack.createRequest('PATCH', 'http://upload');
      request.setHeader('Upload-Offset', '0');

      await request.send(new Blob(['hello world']));

      expect(request.getHeader('Upload-Checksum')).toMatch(/^sha256 /);
    } finally {
      console.error = originalError;
    }
  });

  it('fails when Web Crypto is unavailable', async () => {
    let uploadOptions: any;
    const originalError = console.error;
    console.error = mock(() => {}) as typeof console.error;

    MockUpload.implementation = (_file: any, opts: any) => ({
      start: () => {
        uploadOptions = opts;
        opts.onError(new Error('stop'));
      },
    });

    const originalCrypto = globalThis.crypto;

    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: undefined,
    });

    try {
      const { useTusUpload } = await import('~/composables/useTusUpload');
      const { startTusUpload } = useTusUpload();
      const slot = makeSlot();
      const file = makeFile(10);

      await expect(
        startTusUpload(
          slot,
          'http://upload',
          file,
          'token-123',
          { max_chunk_bytes: 90 * 1024 * 1024 } as any,
          90 * 1024 * 1024,
        ),
      ).rejects.toThrow(Error);
      expect(slot.status).toBe('error');
      expect(slot.error.length).toBeGreaterThan(0);
      expect(uploadOptions).toBeUndefined();
    } finally {
      Object.defineProperty(globalThis, 'crypto', {
        configurable: true,
        value: originalCrypto,
      });
      console.error = originalError;
    }
  });

  it('pauses and resumes existing upload', () => {
    const abort = mock(() => {});
    const start = mock(() => {});
    const slot = makeSlot();
    slot.tusUpload = { abort, start } as any;
    slot.paused = false;
    slot.working = true;

    return import('~/composables/useTusUpload').then(({ useTusUpload }) => {
      const { pauseUpload, resumeUpload } = useTusUpload();
      pauseUpload(slot);
      expect(slot.paused).toBe(true);
      expect(slot.status).toBe('paused');
      expect(slot.working).toBe(false);
      expect(abort).toHaveBeenCalled();

      resumeUpload(slot);
      expect(slot.paused).toBe(false);
      expect(slot.status).toBe('uploading');
      expect(slot.working).toBe(true);
      expect(start).toHaveBeenCalled();
    });
  });
});
