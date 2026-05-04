import * as tus from 'tus-js-client';
import type { ApiError, Slot, UploadRow } from '~/types/uploads';
import type { TokenInfo } from '~/types/token';

const TUS_CHECKSUM_ALGORITHM = 'sha256';
const TUS_WEB_CRYPTO_ALGORITHM = 'SHA-256';
const DEFAULT_MAX_CHUNK_BYTES = 90 * 1024 * 1024;

type ChecksumBody =
  | Blob
  | ArrayBuffer
  | ArrayBufferView
  | { arrayBuffer: () => Promise<ArrayBuffer> };

function resolveChunkSize(
  fileSize: number,
  tokenInfo: TokenInfo | null,
  recommendedChunkBytes?: number | null,
): number {
  const maxChunk = tokenInfo?.max_chunk_bytes || DEFAULT_MAX_CHUNK_BYTES;
  const maxSize = tokenInfo?.max_size_bytes ?? maxChunk;
  const preferredChunk =
    recommendedChunkBytes && recommendedChunkBytes > 0 ? recommendedChunkBytes : maxChunk;

  return Math.max(1, Math.min(preferredChunk, maxChunk, maxSize, fileSize || preferredChunk));
}

function getChecksumSupportError(): Error | null {
  if (!globalThis.crypto?.subtle) {
    return new Error('This browser cannot compute the required upload checksums');
  }

  if (!tus.DefaultHttpStack) {
    return new Error('This browser cannot create checksum-verified uploads');
  }

  return null;
}

async function toArrayBuffer(body: ChecksumBody): Promise<ArrayBuffer> {
  if (body instanceof Blob) {
    if (typeof body.arrayBuffer === 'function') {
      return body.arrayBuffer();
    }

    return new Response(body).arrayBuffer();
  }

  if (body instanceof ArrayBuffer) {
    return body;
  }

  if (ArrayBuffer.isView(body)) {
    return new Uint8Array(body.buffer, body.byteOffset, body.byteLength).slice().buffer;
  }

  if (typeof body.arrayBuffer === 'function') {
    return body.arrayBuffer();
  }

  throw new Error('Unsupported PATCH body for checksum calculation');
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);

  if (typeof btoa === 'function') {
    let binary = '';

    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }

    return btoa(binary);
  }

  const bufferCtor = (
    globalThis as typeof globalThis & {
      Buffer?: { from: (input: Uint8Array) => { toString: (encoding: string) => string } };
    }
  ).Buffer;

  if (bufferCtor) {
    return bufferCtor.from(bytes).toString('base64');
  }

  throw new Error('Base64 encoding is not available in this environment');
}

function getBodySize(body: ChecksumBody): number | null {
  if (body instanceof Blob) {
    return body.size;
  }

  if (body instanceof ArrayBuffer) {
    return body.byteLength;
  }

  if (ArrayBuffer.isView(body)) {
    return body.byteLength;
  }

  return null;
}

function getRequestOffset(request: { getHeader: (header: string) => string | undefined }): number {
  const rawOffset = request.getHeader('Upload-Offset');
  const offset = Number.parseInt(rawOffset || '', 10);

  if (!Number.isFinite(offset) || offset < 0) {
    throw new Error('Upload offset missing for checksum calculation');
  }

  return offset;
}

async function computeUploadChecksum(body: ChecksumBody): Promise<string> {
  const buffer = await toArrayBuffer(body);
  const digest = await globalThis.crypto.subtle.digest(TUS_WEB_CRYPTO_ALGORITHM, buffer);

  return arrayBufferToBase64(digest);
}

function createChecksumHttpStack(file: File, chunkSize: number) {
  const baseStack = new tus.DefaultHttpStack();
  const checksumsByOffset = new Map<number, Promise<string>>();

  function pruneChecksums(currentOffset: number) {
    for (const offset of checksumsByOffset.keys()) {
      if (offset < currentOffset) {
        checksumsByOffset.delete(offset);
      }
    }
  }

  function scheduleChecksum(offset: number, body: ChecksumBody): Promise<string> {
    const existingChecksum = checksumsByOffset.get(offset);
    if (existingChecksum) {
      return existingChecksum;
    }

    const checksumPromise = computeUploadChecksum(body);
    checksumsByOffset.set(offset, checksumPromise);
    return checksumPromise;
  }

  function scheduleLookahead(nextOffset: number) {
    if (nextOffset >= file.size) {
      return;
    }

    const nextEnd = Math.min(nextOffset + chunkSize, file.size);
    scheduleChecksum(nextOffset, file.slice(nextOffset, nextEnd));
  }

  return {
    createRequest(method: string, url: string) {
      const request = baseStack.createRequest(method, url);

      return {
        getMethod: () => request.getMethod(),
        getURL: () => request.getURL(),
        setHeader: (header: string, value: string) => request.setHeader(header, value),
        getHeader: (header: string) => request.getHeader(header),
        setProgressHandler: (progressHandler: (bytesSent: number) => void) =>
          request.setProgressHandler(progressHandler),
        async send(body: ChecksumBody | null) {
          if (request.getMethod() !== 'PATCH' || body == null) {
            return request.send(body);
          }

          const offset = getRequestOffset(request);
          pruneChecksums(offset);

          const checksum = await scheduleChecksum(offset, body);
          request.setHeader('Upload-Checksum', `${TUS_CHECKSUM_ALGORITHM} ${checksum}`);

          const sendPromise = request.send(body);
          const bodySize = getBodySize(body);
          const nextOffset = offset + (bodySize ?? chunkSize);
          scheduleLookahead(nextOffset);

          return sendPromise;
        },
        abort: () => request.abort(),
        getUnderlyingObject: () => request.getUnderlyingObject(),
      };
    },
    getName() {
      return typeof baseStack.getName === 'function'
        ? `Checksum${baseStack.getName()}`
        : 'ChecksumHttpStack';
    },
  };
}

export function useTusUpload() {
  const { $apiFetch } = useNuxtApp();

  async function startTusUpload(
    slot: Slot,
    uploadUrl: string,
    file: File,
    token: string,
    tokenInfo: TokenInfo | null,
    recommendedChunkBytes?: number | null,
    onUploadComplete?: (slot: Slot) => void,
  ) {
    slot.status = 'uploading';
    slot.paused = false;

    const checksumSupportError = getChecksumSupportError();
    if (checksumSupportError) {
      slot.error = checksumSupportError.message;
      slot.status = 'error';
      return Promise.reject(checksumSupportError);
    }

    return new Promise<void>((resolve, reject) => {
      const chunkSize = resolveChunkSize(file.size, tokenInfo, recommendedChunkBytes);
      const httpStack = createChecksumHttpStack(file, chunkSize);
      const upload = new tus.Upload(file, {
        uploadUrl,
        chunkSize,
        retryDelays: [0, 500, 1000, 3000],
        metadata: {
          filename: file.name,
          filetype: file.type,
        },
        httpStack,
        onError(error: Error) {
          slot.error = error.message || String(error);
          slot.status = 'error';
          slot.tusUpload = undefined;
          console.error('TUS upload failed', error);
          reject(error);
        },
        onProgress(bytesUploaded: number, bytesTotal: number) {
          slot.progress = Math.round((bytesUploaded / bytesTotal) * 100);
          slot.bytesUploaded = bytesUploaded;
          slot.status = 'uploading';
        },
        async onSuccess() {
          slot.progress = 100;
          slot.bytesUploaded = file.size;
          slot.tusUpload = undefined;

          if (!slot.uploadId) {
            const error = new Error('Upload ID missing for completion');
            slot.error = error.message;
            slot.status = 'error';
            reject(error);
            return;
          }

          try {
            const completedUpload = await $apiFetch<UploadRow>(
              `/api/uploads/${slot.uploadId}/complete`,
              {
                method: 'POST',
                query: { token },
              },
            );
            slot.status = completedUpload.status;

            if (onUploadComplete) {
              onUploadComplete(slot);
            }

            resolve();
          } catch (err) {
            const error = err as ApiError;
            slot.error = error?.data?.detail || error?.message || 'Failed to finalize upload';
            slot.status = 'error';
            reject(err instanceof Error ? err : new Error(slot.error));
          }
        },
      });

      slot.tusUpload = upload;
      upload.start();
    });
  }

  function pauseUpload(slot: Slot) {
    if (slot.tusUpload && !slot.paused) {
      slot.tusUpload.abort();
      slot.paused = true;
      slot.status = 'paused';
      slot.working = false;
    }
  }

  function resumeUpload(slot: Slot) {
    if (slot.tusUpload && slot.paused) {
      slot.paused = false;
      slot.status = 'uploading';
      slot.working = true;
      slot.tusUpload.start();
    }
  }

  return { startTusUpload, pauseUpload, resumeUpload };
}
