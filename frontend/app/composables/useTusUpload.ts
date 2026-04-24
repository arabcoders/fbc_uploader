import * as tus from 'tus-js-client'
import type { ApiError, Slot, UploadRow } from '~/types/uploads'
import type { TokenInfo } from '~/types/token'

const TUS_CHECKSUM_ALGORITHM = 'sha256'
const TUS_WEB_CRYPTO_ALGORITHM = 'SHA-256'
const TUS_CHECKSUM_MAX_CHUNK_BYTES = 16 * 1024 * 1024

function resolveChunkSize(tokenInfo: TokenInfo | null): number {
  const maxChunk = tokenInfo?.max_chunk_bytes || 90 * 1024 * 1024
  const maxSize = tokenInfo?.max_size_bytes ?? maxChunk

  return Math.min(maxChunk, maxSize, TUS_CHECKSUM_MAX_CHUNK_BYTES)
}

async function toArrayBuffer(body: Blob | ArrayBuffer | ArrayBufferView | { arrayBuffer: () => Promise<ArrayBuffer> }): Promise<ArrayBuffer> {
  if (body instanceof Blob) {
    if (typeof body.arrayBuffer === 'function') {
      return body.arrayBuffer()
    }

    return new Response(body).arrayBuffer()
  }

  if (body instanceof ArrayBuffer) {
    return body
  }

  if (ArrayBuffer.isView(body)) {
    return new Uint8Array(body.buffer, body.byteOffset, body.byteLength).slice().buffer
  }

  if (typeof body.arrayBuffer === 'function') {
    return body.arrayBuffer()
  }

  throw new Error('Unsupported PATCH body for checksum calculation')
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)

  if (typeof btoa === 'function') {
    let binary = ''

    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
    }

    return btoa(binary)
  }

  const bufferCtor = (globalThis as typeof globalThis & {
    Buffer?: { from: (input: Uint8Array) => { toString: (encoding: string) => string } }
  }).Buffer

  if (bufferCtor) {
    return bufferCtor.from(bytes).toString('base64')
  }

  throw new Error('Base64 encoding is not available in this environment')
}

async function computeUploadChecksum(body: Blob | ArrayBuffer | ArrayBufferView | { arrayBuffer: () => Promise<ArrayBuffer> }): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Web Crypto is not available for checksum calculation')
  }

  const buffer = await toArrayBuffer(body)
  const digest = await globalThis.crypto.subtle.digest(TUS_WEB_CRYPTO_ALGORITHM, buffer)

  return arrayBufferToBase64(digest)
}

function createChecksumHttpStack() {
  if (!tus.DefaultHttpStack) {
    return undefined
  }

  const baseStack = new tus.DefaultHttpStack()

  return {
    createRequest(method: string, url: string) {
      const request = baseStack.createRequest(method, url)

      return {
        getMethod: () => request.getMethod(),
        getURL: () => request.getURL(),
        setHeader: (header: string, value: string) => request.setHeader(header, value),
        getHeader: (header: string) => request.getHeader(header),
        setProgressHandler: (progressHandler: (bytesSent: number) => void) => request.setProgressHandler(progressHandler),
        async send(body: Blob | ArrayBuffer | ArrayBufferView | { arrayBuffer: () => Promise<ArrayBuffer> } | null) {
          if (request.getMethod() === 'PATCH' && body != null) {
            const checksum = await computeUploadChecksum(body)
            request.setHeader('Upload-Checksum', `${TUS_CHECKSUM_ALGORITHM} ${checksum}`)
          }

          return request.send(body)
        },
        abort: () => request.abort(),
        getUnderlyingObject: () => request.getUnderlyingObject(),
      }
    },
    getName() {
      return typeof baseStack.getName === 'function' ? `Checksum${baseStack.getName()}` : 'ChecksumHttpStack'
    },
  }
}

export function useTusUpload() {
  const { $apiFetch } = useNuxtApp()

  async function startTusUpload(
    slot: Slot,
    uploadUrl: string,
    file: File,
    token: string,
    tokenInfo: TokenInfo | null,
    onUploadComplete?: (slot: Slot) => void
  ) {
    slot.status = 'uploading'
    slot.paused = false

    return new Promise<void>((resolve, reject) => {
      const httpStack = createChecksumHttpStack()
      const chunkSize = Math.min(resolveChunkSize(tokenInfo), file.size || resolveChunkSize(tokenInfo))
      const upload = new tus.Upload(file, {
        uploadUrl,
        chunkSize,
        retryDelays: [0, 500, 1000, 3000],
        metadata: {
          filename: file.name,
          filetype: file.type,
        },
        ...(httpStack ? { httpStack } : {}),
        onError(error: Error) {
          slot.error = error.message
          slot.status = 'error'
          slot.tusUpload = undefined
          reject(error)
        },
        onProgress(bytesUploaded: number, bytesTotal: number) {
          slot.progress = Math.round((bytesUploaded / bytesTotal) * 100)
          slot.bytesUploaded = bytesUploaded
          slot.status = 'uploading'
        },
        async onSuccess() {
          slot.progress = 100
          slot.bytesUploaded = file.size
          slot.tusUpload = undefined

          if (!slot.uploadId) {
            const error = new Error('Upload ID missing for completion')
            slot.error = error.message
            slot.status = 'error'
            reject(error)
            return
          }

          try {
            const completedUpload = await $apiFetch<UploadRow>(`/api/uploads/${slot.uploadId}/complete`, {
              method: 'POST',
              query: { token },
            })
            slot.status = completedUpload.status

            if (onUploadComplete) {
              onUploadComplete(slot)
            }

            resolve()
          } catch (err) {
            const error = err as ApiError
            slot.error = error?.data?.detail || error?.message || 'Failed to finalize upload'
            slot.status = 'error'
            reject(err instanceof Error ? err : new Error(slot.error))
          }
        },
      })

      slot.tusUpload = upload
      upload.start()
    })
  }

  function pauseUpload(slot: Slot) {
    if (slot.tusUpload && !slot.paused) {
      slot.tusUpload.abort()
      slot.paused = true
      slot.status = 'paused'
      slot.working = false
    }
  }

  function resumeUpload(slot: Slot) {
    if (slot.tusUpload && slot.paused) {
      slot.paused = false
      slot.status = 'uploading'
      slot.working = true
      slot.tusUpload.start()
    }
  }

  return { startTusUpload, pauseUpload, resumeUpload }
}
