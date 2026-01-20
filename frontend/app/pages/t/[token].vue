<template>
  <UContainer class="py-10">
    <div class="space-y-6">
      <div v-if="notFound && !tokenInfo">
        <UAlert color="error" variant="solid" :title="tokenError || 'Token not found'"
          icon="i-heroicons-exclamation-triangle-20-solid"
          :ui="{ title: 'text-lg font-semibold', description: 'text-base' }" />
      </div>

      <div v-else-if="tokenInfo && (isExpired || isDisabled)">
        <UAlert v-if="isExpired" color="warning" variant="soft" title="Token has expired"
          description="This upload token has expired and can no longer be used." icon="i-heroicons-clock-20-solid"
          :ui="{ title: 'text-lg font-semibold', description: 'text-base' }" />
        <UAlert v-else-if="isDisabled" color="warning" variant="soft" title="Token is disabled"
          description="This token has been disabled and can no longer be used." icon="i-heroicons-lock-closed-20-solid"
          :ui="{ title: 'text-lg font-semibold', description: 'text-base' }" />
      </div>

      <template v-else-if="tokenInfo">
        <div class="space-y-4">
          <TokenSummary :token-info="tokenInfo" :share-link="shareLinkText" @copy="copyShareLink"
            @refresh="refreshAll" />
        </div>

        <UCard v-if="notice" variant="outline">
          <template #header>
            <UCollapsible v-model:open="showNotice">
              <button class="group flex items-center gap-2 w-full cursor-pointer">
                <UIcon name="i-heroicons-megaphone-20-solid" />
                <span class="font-semibold">System Notice</span>
                <UIcon name="i-heroicons-chevron-down-20-solid"
                  class="ml-auto group-data-[state=open]:rotate-180 transition-transform duration-200" />
              </button>

              <template #content>
                <div class="px-4 sm:px-6 pb-4 sm:pb-6">
                  <Markdown :content="notice" class="prose dark:prose-invert max-w-7xl" />
                </div>
              </template>
            </UCollapsible>
          </template>
        </UCard>

        <div v-if="allRows.length > 0" class="space-y-3">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-list-bullet-20-solid" />
            <h2 class="text-lg font-semibold">Uploads</h2>
          </div>
          <UploadsTable :rows="allRows" :allow-downloads="tokenInfo?.allow_public_downloads ?? false"
            @resume="handleResume" @pause="handlePause" @cancel="handleCancel" />
        </div>

        <div v-else-if="!showForms" class="max-w-full">
          <UAlert color="neutral" variant="outline" title="No uploads yet"
            description="All upload slots for this token have been used. There are no files uploaded yet."
            icon="i-heroicons-inbox-20-solid" />
        </div>

        <div v-if="showForms" class="space-y-4">
          <div class="grid gap-4 md:grid-cols-2">
            <UploadSlotCard v-for="(slot, idx) in unintiatedSlots" :key="idx" :index="idx" :upload-slot="slot"
              :metadata-schema="metadataSchema" :accept-attr="acceptAttr" @file="(e: Event) => onFile(slot, e)"
              @meta="(v) => onMetaChange(slot, v)" @start="start(slot, idx)" />
          </div>
          <UButton v-if="canAddMoreSlots" color="neutral" variant="outline" icon="i-heroicons-plus-20-solid"
            @click="addSlot">
            Add another upload ({{ (tokenInfo?.remaining_uploads || 0) - unintiatedSlots.length }} remaining)
          </UButton>
        </div>
      </template>
    </div>
    <input ref="resumeInput" type="file" class="hidden" @change="onResumeFile" />
  </UContainer>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import type { UploadRow, Slot, UploadRowWithSlot, InitiateUploadResponse, CancelUploadResponse, ApiError } from '~/types/uploads'
import { useTokenInfo } from '~/composables/useTokenInfo'
import { useMetadata } from '~/composables/useMetadata'
import { useMetadataParser } from '~/composables/useMetadataParser'
import { validateSlot } from '~/utils/validation'
import { useTusUpload } from '~/composables/useTusUpload'
import { useUploadSlots } from '~/composables/useUploadSlots'
import { useUploadPolling } from '~/composables/useUploadPolling'
import { useStorage } from '@vueuse/core'

const route = useRoute()
const toast = useToast()
const token = ref<string>((route.params.token as string) || '')

const { tokenInfo, notFound, tokenError, isExpired, isDisabled, shareLinkText, fetchTokenInfo } = useTokenInfo(token)
const { metadataSchema, fetchMetadata } = useMetadata()
const { applyParsedMeta } = useMetadataParser()
const { startTusUpload, pauseUpload, resumeUpload } = useTusUpload()
const { slots, seedSlots, addSlot, unintiatedSlots } = useUploadSlots(metadataSchema)
const { pollUploadStatus, stopPolling, stopAllPolling } = useUploadPolling()

const notice = ref<string>('')

const results = ref<Record<number, any>>({})
const resumeTarget = ref<UploadRow | null>(null)
const resumeInput = ref<HTMLInputElement | null>(null)
const showNotice = useStorage<boolean>('show_notice', true)

const showForms = computed(() => tokenInfo.value &&
  !isExpired.value && !isDisabled.value &&
  (tokenInfo.value.remaining_uploads > 0 || slots.value.some((s) => s.status && s.status !== 'completed'))
)

const canAddMoreSlots = computed(() => tokenInfo.value && unintiatedSlots.value.length < (tokenInfo.value.remaining_uploads || 0))

const allRows = computed(() => {
  const completed = tokenInfo.value?.uploads || []
  const active = slots.value
    .filter((s) => s.initiated)
    .map((s) => {
      const fileSize = s.file?.size ?? 0
      const uploadedBytes = s.bytesUploaded ?? Math.floor((s.progress / 100) * fileSize)
      return {
        public_id: s.uploadId || '',
        filename: s.file?.name || '',
        status: s.status,
        upload_offset: uploadedBytes,
        upload_length: fileSize,
        size_bytes: fileSize,
        meta_data: s.values,
        slot: s,
        _reactiveKey: `${s.bytesUploaded}-${s.progress}-${s.status}`,
      }
    })

  const activeIds = new Set(active.map(a => a.public_id))
  const nonDuplicateCompleted = completed.filter(c => !activeIds.has(c.public_id))

  return [...active, ...nonDuplicateCompleted]
})

const acceptAttr = computed(() => {
  if (!tokenInfo.value?.allowed_mime || !tokenInfo.value.allowed_mime.length) return undefined
  return tokenInfo.value.allowed_mime.join(',')
})

async function refreshAll() {
  await fetchTokenInfo()
  await fetchMetadata()
  seedSlots(tokenInfo.value)
}

function onFile(slot: Slot, e: Event) {
  const target = e.target as HTMLInputElement
  slot.file = target.files?.[0] || null
  metadataSchema.value.forEach((f) => (slot.values[f.key] = f.default ?? ''))
  if (slot.file) applyParsedMeta(slot, slot.file.name, metadataSchema.value)
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value)
}

function onMetaChange(slot: Slot, values: Record<string, any>) {
  slot.values = values
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value)
}

async function copyShareLink() {
  if (!shareLinkText.value) return
  copyText(shareLinkText.value)
  toast.add({
    title: 'Share link copied to clipboard',
    color: 'success',
    icon: 'i-heroicons-check-circle-20-solid',
  })
}

async function start(slot: Slot, idx: number) {
  if (!tokenInfo.value) {
    slot.error = 'Token missing or expired.'
    return
  }
  slot.errors = validateSlot(slot, metadataSchema.value, tokenInfo.value)
  if (!slot.file || slot.errors.length) {
    slot.error = slot.errors.join('; ') || 'Fill all metadata and select a file.'
    slot.status = 'validation_failed'
    return
  }
  slot.error = ''
  slot.working = true
  slot.status = 'initiating'
  try {
    const res = await $fetch<InitiateUploadResponse>(`/api/uploads/initiate`, {
      method: 'POST',
      query: { token: token.value },
      body: {
        meta_data: slot.values,
        filename: slot.file.name,
        filetype: slot.file.type,
        size_bytes: slot.file.size,
      },
    })
    results.value[idx] = res
    slot.uploadId = res.upload_id
    slot.initiated = true

    // Decrement remaining_uploads locally since backend consumes upload on initiation
    if (tokenInfo.value && res.remaining_uploads !== undefined) {
      tokenInfo.value.remaining_uploads = res.remaining_uploads
    }

    if (slot.file) {
      await startTusUpload(slot, res.upload_url, slot.file, tokenInfo.value, (completedSlot) => {
        if (completedSlot.status === 'postprocessing' && completedSlot.uploadId) {
          pollUploadStatus(completedSlot.uploadId, token.value, completedSlot, refreshAll)
        }
      })
      await refreshAll()
    }
  } catch (err) {
    const error = err as ApiError
    slot.error = error?.data?.detail || error?.message || 'Failed to initiate upload'
    slot.status = 'error'
  } finally {
    slot.working = false
  }
}

function handlePause(row: UploadRowWithSlot) {
  if (row.slot) {
    pauseUpload(row.slot)
  }
}

function handleResume(row: UploadRowWithSlot) {
  if (row.slot) {
    resumeUpload(row.slot)
  } else {
    triggerResume(row)
  }
}

async function handleCancel(row: UploadRowWithSlot) {
  if (!row.public_id || row.status === 'completed') return

  try {
    const res = await $fetch<CancelUploadResponse>(`/api/uploads/${row.public_id}/cancel`, {
      method: 'DELETE',
      query: { token: token.value },
    })

    if (tokenInfo.value && res.remaining_uploads !== undefined) {
      tokenInfo.value.remaining_uploads = res.remaining_uploads
    }

    stopPolling(row.public_id)

    if (row.slot) {
      const slotIndex = slots.value.indexOf(row.slot)
      if (slotIndex > -1) {
        slots.value.splice(slotIndex, 1)
      }
    }

    toast.add({
      title: 'Upload cancelled',
      description: 'Upload slot has been restored',
      color: 'success',
      icon: 'i-heroicons-check-circle-20-solid',
    })

    await refreshAll()
  } catch (err) {
    const error = err as ApiError
    toast.add({
      title: 'Failed to cancel upload',
      description: error?.data?.detail || error?.message || 'Unknown error',
      color: 'error',
      icon: 'i-heroicons-exclamation-triangle-20-solid',
    })
  }
}

function triggerResume(upload: UploadRow) {
  resumeTarget.value = upload
  resumeInput.value?.click()
}

async function onResumeFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !resumeTarget.value || !resumeTarget.value.upload_url) {
    resumeTarget.value = null
    return
  }

  if (file.name !== resumeTarget.value.filename) {
    toast.add({
      title: 'File name mismatch',
      description: `Expected: ${resumeTarget.value.filename}, Got: ${file.name}`,
      color: 'error',
      icon: 'i-heroicons-exclamation-triangle-20-solid',
    })
    if (resumeInput.value) resumeInput.value.value = ''
    resumeTarget.value = null
    return
  }

  if (file.size !== resumeTarget.value.upload_length) {
    toast.add({
      title: 'File size mismatch',
      description: `Expected: ${resumeTarget.value.upload_length} bytes, Got: ${file.size} bytes`,
      color: 'error',
      icon: 'i-heroicons-exclamation-triangle-20-solid',
    })
    if (resumeInput.value) resumeInput.value.value = ''
    resumeTarget.value = null
    return
  }

  const resumeSlot = reactive<Slot>({
    file,
    values: resumeTarget.value.meta_data || {},
    error: '',
    working: true,
    progress: Math.round(((resumeTarget.value.upload_offset || 0) / (resumeTarget.value.upload_length || 1)) * 100),
    bytesUploaded: resumeTarget.value.upload_offset || 0,
    status: 'resuming',
    errors: [],
    paused: false,
    initiated: true,
    uploadId: resumeTarget.value.public_id,
  })

  slots.value.push(resumeSlot)

  try {
    await startTusUpload(resumeSlot, resumeTarget.value.upload_url, file, tokenInfo.value, (completedSlot) => {
      if (completedSlot.status === 'postprocessing' && completedSlot.uploadId) {
        pollUploadStatus(completedSlot.uploadId, token.value, completedSlot, refreshAll)
      }
    })
    await refreshAll()
  } catch (err) {
    const error = err as ApiError
    resumeSlot.error = error?.message || 'Resume failed'
    resumeSlot.status = 'error'
  } finally {
    if (resumeInput.value) resumeInput.value.value = ''
    resumeTarget.value = null
  }
}

watch(() => route.query.token, (val) => {
  if (typeof val === 'string') {
    token.value = val
    refreshAll()
  }
}, { immediate: true })

onMounted(async () => {
  if (token.value) refreshAll()
  else notFound.value = true

  const notice_req = await $fetch<{ notice: string | null }>('/api/notice/')
  if (notice_req.notice) {
    notice.value = notice_req.notice
  }
})

onUnmounted(() => {
  stopAllPolling()
})
</script>
