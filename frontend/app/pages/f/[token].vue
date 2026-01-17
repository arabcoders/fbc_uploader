<template>
  <UContainer class="py-10">
    <div class="space-y-6">
      <div v-if="notFound && !tokenInfo">
        <UAlert color="error" variant="solid" :title="tokenError || 'Token not found'"
          icon="i-heroicons-exclamation-triangle-20-solid" />
      </div>

      <div v-if="tokenInfo && (isExpired || isDisabled)">
        <UAlert v-if="isExpired" color="warning" variant="soft" title="Token has expired"
          icon="i-heroicons-clock-20-solid" />
        <UAlert v-else-if="isDisabled" color="warning" variant="soft" title="Token is disabled"
          icon="i-heroicons-lock-closed-20-solid" />
      </div>

      <div v-if="tokenInfo" class="space-y-4">
        <UCard>
          <div class="space-y-4">
            <div class="flex items-start justify-between gap-4">
              <div class="space-y-1">
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-share-20-solid" class="size-5 text-primary" />
                  <h1 class="text-2xl font-bold">Shared Files</h1>
                </div>
                <p class="text-muted">
                  {{ uploads.length }} {{ uploads.length === 1 ? 'file' : 'files' }} available
                </p>
              </div>
              <UButton v-if="shareUrl" color="neutral" variant="outline" icon="i-heroicons-clipboard-document-20-solid"
                @click="copyShareUrl">
                Copy Link
              </UButton>
            </div>

            <div class="flex flex-wrap gap-4 text-sm">
              <div class="flex items-center gap-2">
                <UIcon name="i-heroicons-calendar-20-solid" class="size-4 text-muted" />
                <span class="text-muted">Expires:</span>
                <span class="font-medium">{{ formatDate(tokenInfo.expires_at) }}</span>
              </div>
              <div v-if="tokenInfo.allowed_mime?.length" class="flex items-center gap-2">
                <UIcon name="i-heroicons-document-20-solid" class="size-4 text-muted" />
                <span class="text-muted">Types:</span>
                <span class="font-medium">{{ tokenInfo.allowed_mime.join(', ') }}</span>
              </div>
              <div class="flex items-center gap-2">
                <UIcon
                  :name="tokenInfo.allow_public_downloads ? 'i-heroicons-lock-open-20-solid' : 'i-heroicons-lock-closed-20-solid'"
                  class="size-4 text-muted" />
                <span class="font-medium">
                  {{ tokenInfo.allow_public_downloads ? 'Public downloads enabled' : 'Downloads require authentication'
                  }}
                </span>
              </div>
            </div>
          </div>
        </UCard>
      </div>
      <UCard v-if="!notFound && notice" variant="outline">
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

      <div v-if="uploads.length > 0" class="space-y-3">
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-folder-open-20-solid" />
          <h2 class="text-lg font-semibold">Files</h2>
        </div>

        <div class="overflow-x-auto rounded-lg ring ring-default">
          <table class="w-full divide-y divide-default">
            <thead class="bg-elevated">
              <tr>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted min-w-48">Filename</th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-32">Status</th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-30">Size</th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-50">Uploaded</th>
              </tr>
            </thead>
            <tbody class="bg-default divide-y divide-default">
              <tr v-for="upload in uploads" :key="upload.id" class="hover:bg-elevated/50 transition-colors">
                <td class="px-4 py-3 text-sm">
                  <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
                    <div class="flex items-center gap-2">
                      <UIcon :name="getFileIcon(upload.filename || '')" class="size-5 text-primary shrink-0" />
                      <span class="font-medium break-all">
                        <NuxtLink
                          v-if="tokenInfo?.allow_public_downloads && upload.status === 'completed' && upload.download_url"
                          :to="upload.download_url">
                          {{ upload.filename }}
                        </NuxtLink>
                        <span v-else>
                          {{ upload.filename }}
                        </span>
                      </span>
                    </div>
                    <template #content>
                      <div class="space-y-3 text-sm min-w-64 max-w-96">
                        <div class="font-semibold text-highlighted">File Details</div>
                        <div class="space-y-2">
                          <div class="grid grid-cols-[auto_1fr] gap-2">
                            <span class="text-muted font-medium">ID:</span>
                            <span>{{ upload.id }}</span>
                          </div>
                          <div v-if="upload.mimetype" class="grid grid-cols-[auto_1fr] gap-2">
                            <span class="text-muted font-medium">Type:</span>
                            <span>{{ upload.mimetype }}</span>
                          </div>
                        </div>
                        <div v-if="hasMetadata(upload.meta_data)" class="space-y-2 pt-2 border-t border-default">
                          <div class="font-semibold text-highlighted">Metadata</div>
                          <div v-for="(val, key) in filterMetadata(upload.meta_data)" :key="key"
                            class="grid grid-cols-[auto_1fr] gap-2">
                            <span class="text-muted font-medium capitalize">{{ formatKey(key) }}:</span>
                            <span class="wrap-break-word">{{ formatValue(val) }}</span>
                          </div>
                        </div>
                      </div>
                    </template>
                  </UPopover>
                </td>
                <td class="px-4 py-3 text-sm">
                  <UBadge :color="getStatusColor(upload.status)" variant="soft">
                    {{ upload.status }}
                  </UBadge>
                </td>
                <td class="px-4 py-3 text-sm font-medium">
                  {{ formatBytes(upload.size_bytes || 0) }}
                </td>
                <td class="px-4 py-3 text-sm text-muted">
                  {{ formatDate(upload.created_at) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="tokenInfo && !loading" class="max-w-full">
        <UAlert color="neutral" variant="outline" title="No files available"
          description="There are no uploaded files to display for this token." icon="i-heroicons-inbox-20-solid" />
      </div>

      <div v-if="loading" class="flex justify-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="size-8 animate-spin text-primary" />
      </div>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { formatBytes, formatDate, formatKey, formatValue, copyText } from '~/utils'
import { useStorage } from '@vueuse/core'
import { useTokenInfo } from '~/composables/useTokenInfo'

const route = useRoute()
const toast = useToast()
const token = ref<string>((route.params.token as string) || '')

const { tokenInfo, notFound, tokenError, isExpired, isDisabled, fetchTokenInfo } = useTokenInfo(token)
const loading = ref(true)
const notice = ref<string>('')
const showNotice = useStorage<boolean>('show_notice', true)

const uploads = computed(() => {
  return tokenInfo.value?.uploads?.filter(u => u.status === 'completed') || []
})

const shareUrl = computed(() => {
  if (!token.value) return ''
  return `${window.location.origin}/f/${token.value}`
})

function copyShareUrl() {
  copyText(shareUrl.value)
  toast.add({
    title: 'Share link copied to clipboard',
    color: 'success',
    icon: 'i-heroicons-check-circle-20-solid',
  })
}

function getStatusColor(status: string): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'completed': return 'success'
    case 'error':
    case 'validation_failed': return 'error'
    case 'in_progress':
    case 'uploading': return 'warning'
    default: return 'neutral'
  }
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'pdf': return 'i-heroicons-document-text-20-solid'
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'webp': return 'i-heroicons-photo-20-solid'
    case 'mp4':
    case 'mov':
    case 'avi':
    case 'mkv': return 'i-heroicons-film-20-solid'
    case 'mp3':
    case 'wav':
    case 'flac': return 'i-heroicons-musical-note-20-solid'
    case 'zip':
    case 'rar':
    case '7z': return 'i-heroicons-archive-box-20-solid'
    case 'doc':
    case 'docx': return 'i-heroicons-document-20-solid'
    default: return 'i-heroicons-document-20-solid'
  }
}

function filterMetadata(meta_data: Record<string, any> | undefined): Record<string, any> {
  if (!meta_data) return {}
  const { ffprobe, ...filtered } = meta_data
  return filtered
}

function hasMetadata(meta_data: Record<string, any> | undefined): boolean {
  const filtered = filterMetadata(meta_data)
  return Object.keys(filtered).length > 0
}

onMounted(async () => {
  if (!token.value) {
    notFound.value = true
    loading.value = false
    return
  }

  await fetchTokenInfo()
  loading.value = false

  // Fetch notice
  try {
    const noticeData = await $fetch<{ notice: string | null }>('/api/notice/')
    if (noticeData.notice) {
      notice.value = noticeData.notice
    }
  } catch {
    // Ignore notice fetch errors
  }
})

useHead({
  title: 'Shared Files'
})
</script>
