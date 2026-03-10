import * as tus from 'tus-js-client'
import type { ApiError, Slot, UploadRow } from '~/types/uploads'
import type { TokenInfo } from '~/types/token'

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
            const maxChunk = tokenInfo?.max_chunk_bytes || 90 * 1024 * 1024
            const chunkSize = tokenInfo?.max_size_bytes ? Math.min(maxChunk, tokenInfo.max_size_bytes) : maxChunk
            const upload = new tus.Upload(file, {
                uploadUrl: uploadUrl,
                chunkSize,
                retryDelays: [0, 500, 1000, 3000],
                metadata: {
                    filename: file.name,
                    filetype: file.type,
                },
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
