<template>
  <UContainer class="py-10">
    <div class="space-y-6">
      <div v-if="notFound && !tokenInfo">
        <UAlert
          color="error"
          variant="solid"
          :title="tokenError || 'Token not found'"
          icon="i-heroicons-exclamation-triangle-20-solid"
        />
      </div>

      <div v-if="tokenInfo && (isExpired || isDisabled)">
        <UAlert
          v-if="isExpired"
          color="warning"
          variant="soft"
          title="Token has expired"
          icon="i-heroicons-clock-20-solid"
        />
        <UAlert
          v-else-if="isDisabled"
          color="warning"
          variant="soft"
          title="Token is disabled"
          icon="i-heroicons-lock-closed-20-solid"
        />
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
              <UButton
                v-if="shareUrl"
                color="neutral"
                variant="outline"
                icon="i-heroicons-clipboard-document-20-solid"
                @click="copyShareUrl"
              >
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
                  :name="
                    tokenInfo.allow_public_downloads
                      ? 'i-heroicons-lock-open-20-solid'
                      : 'i-heroicons-lock-closed-20-solid'
                  "
                  class="size-4 text-muted"
                />
                <span class="font-medium">
                  {{
                    tokenInfo.allow_public_downloads
                      ? 'Public downloads enabled'
                      : 'Downloads require authentication'
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
              <UIcon
                name="i-heroicons-chevron-down-20-solid"
                class="ml-auto group-data-[state=open]:rotate-180 transition-transform duration-200"
              />
            </button>

            <template #content>
              <div class="px-4 sm:px-6 pb-4 sm:pb-6">
                <Markdown :content="notice" class="max-w-7xl" />
              </div>
            </template>
          </UCollapsible>
        </template>
      </UCard>

      <UCard
        v-if="canPlaySelectedMedia && selectedUpload"
        class="max-w-full overflow-hidden"
        :ui="{ body: 'p-0 sm:p-0', root: 'overflow-hidden' }"
      >
        <div
          class="grid min-w-0 max-w-full gap-0 xl:grid-cols-[minmax(0,2fr)_24rem] xl:items-stretch"
        >
          <div
            class="min-w-0 max-w-full overflow-hidden border-b border-default bg-elevated/40 xl:border-b-0 xl:border-r"
          >
            <div
              class="flex flex-col gap-3 border-b border-default bg-default/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-muted">
                  <UIcon
                    :name="
                      selectedIsVideo
                        ? 'i-heroicons-film-20-solid'
                        : 'i-heroicons-musical-note-20-solid'
                    "
                    class="size-4"
                  />
                  <span>{{
                    shouldRenderSelectedMedia
                      ? selectedIsVideo
                        ? 'Now playing'
                        : 'Now listening'
                      : 'Ready to preview'
                  }}</span>
                </div>
                <h2 class="mt-1 truncate text-lg font-semibold text-highlighted">
                  {{ selectedUpload.filename || 'Untitled media' }}
                </h2>
              </div>
              <a
                v-if="selectedUpload.download_url"
                :href="selectedUpload.download_url"
                class="w-full sm:w-auto"
              >
                <UButton
                  color="neutral"
                  variant="outline"
                  icon="i-heroicons-arrow-down-tray-20-solid"
                  size="sm"
                >
                  Download
                </UButton>
              </a>
            </div>

            <div v-if="selectedIsVideo" class="min-w-0 max-w-full overflow-hidden bg-black">
              <div
                class="flex w-full max-w-full items-center justify-center overflow-hidden bg-black p-2 sm:p-0"
              >
                <button
                  v-if="!shouldRenderSelectedMedia"
                  type="button"
                  class="group relative block h-auto max-h-[70vh] w-full max-w-full overflow-hidden bg-black text-left sm:max-h-[72vh]"
                  @click="activateSelectedMedia"
                >
                  <img
                    v-if="selectedThumbnailUrl"
                    :src="selectedThumbnailUrl"
                    :alt="`${selectedUpload.filename || 'Untitled media'} preview`"
                    class="block h-auto max-h-[70vh] w-full max-w-full bg-black object-contain opacity-90 transition duration-200 group-hover:opacity-100 sm:max-h-[72vh]"
                  />
                  <div
                    v-else
                    class="flex min-h-64 w-full items-center justify-center bg-black/90 text-white/80"
                  >
                    <UIcon name="i-heroicons-film-20-solid" class="size-12" />
                  </div>
                  <div
                    class="pointer-events-none absolute inset-0 bg-linear-to-t from-black/70 via-transparent to-black/20"
                  />
                  <div
                    class="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-4 px-4 py-4 sm:px-6"
                  >
                    <div class="min-w-0">
                      <div class="text-xs uppercase tracking-[0.2em] text-white/70">
                        Video Preview
                      </div>
                      <div class="mt-1 truncate text-lg font-semibold text-white">
                        {{ selectedUpload.filename || 'Untitled media' }}
                      </div>
                    </div>
                    <div
                      class="flex size-16 shrink-0 items-center justify-center rounded-full bg-white/12 text-white backdrop-blur ring-1 ring-white/25"
                    >
                      <UIcon name="i-heroicons-play-20-solid" class="ml-1 size-8" />
                    </div>
                  </div>
                </button>
                <video
                  v-else
                  ref="mediaElement"
                  :key="selectedUpload.public_id"
                  class="block h-auto max-h-[70vh] w-full max-w-full bg-black object-contain sm:max-h-[72vh]"
                  controls
                  playsinline
                  preload="metadata"
                  :poster="selectedThumbnailUrl || undefined"
                  @error="handleMediaPlaybackError"
                  @loadedmetadata="clearMediaPlaybackError"
                  @play="clearMediaPlaybackError"
                  @volumechange="handleMediaVolumeChange"
                >
                  <source :src="selectedMediaUrl" :type="selectedUpload.mimetype || undefined" />
                  Your browser does not support the video tag.
                </video>
              </div>
            </div>

            <div v-else class="px-4 py-10 sm:px-6 lg:px-8">
              <div class="rounded-2xl border border-default bg-default p-6 sm:p-8 shadow-sm">
                <button
                  v-if="!shouldRenderSelectedMedia"
                  type="button"
                  class="group block w-full rounded-2xl text-left"
                  @click="activateSelectedMedia"
                >
                  <div
                    class="overflow-hidden rounded-2xl border border-default bg-elevated/80 shadow-sm"
                  >
                    <img
                      v-if="selectedThumbnailUrl"
                      :src="selectedThumbnailUrl"
                      :alt="`${selectedUpload.filename || 'Untitled audio'} preview`"
                      class="block h-auto w-full object-cover transition duration-200 group-hover:scale-[1.01] group-hover:opacity-100"
                    />
                    <div
                      v-else
                      class="flex min-h-56 items-center justify-center bg-linear-to-br from-primary/15 via-default to-elevated text-primary"
                    >
                      <UIcon name="i-heroicons-musical-note-20-solid" class="size-16" />
                    </div>
                    <div
                      class="flex items-center justify-between gap-4 border-t border-default bg-default/95 px-5 py-4"
                    >
                      <div class="min-w-0">
                        <div class="text-xs uppercase tracking-[0.2em] text-muted">
                          Audio Preview
                        </div>
                        <div class="mt-1 truncate text-lg font-semibold text-highlighted">
                          {{ selectedUpload.filename || 'Untitled audio' }}
                        </div>
                      </div>
                      <div
                        class="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary ring ring-default"
                      >
                        <UIcon name="i-heroicons-play-20-solid" class="ml-0.5 size-7" />
                      </div>
                    </div>
                  </div>
                </button>
                <div v-else class="flex items-center gap-3 text-highlighted">
                  <div
                    class="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary ring ring-default"
                  >
                    <UIcon name="i-heroicons-musical-note-20-solid" class="size-6" />
                  </div>
                  <div>
                    <div class="text-xs uppercase tracking-wide text-muted">Audio Preview</div>
                    <div class="text-lg font-semibold">
                      {{ selectedUpload.filename || 'Untitled audio' }}
                    </div>
                  </div>
                </div>
                <audio
                  v-if="shouldRenderSelectedMedia"
                  ref="mediaElement"
                  :key="selectedUpload.public_id"
                  class="mt-6 w-full"
                  controls
                  preload="metadata"
                  @error="handleMediaPlaybackError"
                  @loadedmetadata="clearMediaPlaybackError"
                  @play="clearMediaPlaybackError"
                  @volumechange="handleMediaVolumeChange"
                >
                  <source :src="selectedMediaUrl" :type="selectedUpload.mimetype || undefined" />
                  Your browser does not support the audio tag.
                </audio>
              </div>
            </div>

            <div
              v-if="mediaPlaybackError"
              class="border-t border-default bg-default px-4 py-4 sm:px-5"
            >
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div class="space-y-1">
                  <div class="text-sm font-medium text-highlighted">Playback issue</div>
                  <p class="text-sm text-muted">{{ mediaPlaybackError }}</p>
                </div>
                <a
                  v-if="selectedUpload.download_url"
                  :href="selectedUpload.download_url"
                  class="shrink-0"
                >
                  <UButton
                    color="neutral"
                    variant="outline"
                    icon="i-heroicons-arrow-down-tray-20-solid"
                    size="sm"
                  >
                    Download Original
                  </UButton>
                </a>
              </div>
            </div>
          </div>

          <div class="min-w-0 bg-default/60">
            <div class="space-y-6 p-4 sm:p-5">
              <div class="space-y-3">
                <div class="flex items-center gap-2 text-sm font-semibold text-highlighted">
                  <UIcon
                    name="i-heroicons-information-circle-20-solid"
                    class="size-5 text-primary"
                  />
                  <span>Current Source</span>
                </div>
                <div class="grid gap-3 text-sm">
                  <div class="flex items-center justify-between gap-4">
                    <span class="text-muted">Type</span>
                    <span class="text-right font-medium">{{
                      selectedUpload.mimetype || 'Unknown'
                    }}</span>
                  </div>
                  <div class="flex items-center justify-between gap-4">
                    <span class="text-muted">Size</span>
                    <span class="text-right font-medium">{{
                      formatBytes(selectedUpload.size_bytes || 0) || 'Unknown'
                    }}</span>
                  </div>
                  <div v-if="selectedDurationLabel" class="flex items-center justify-between gap-4">
                    <span class="text-muted">Duration</span>
                    <span class="text-right font-medium">{{ selectedDurationLabel }}</span>
                  </div>
                  <div
                    v-if="selectedResolutionLabel"
                    class="flex items-center justify-between gap-4"
                  >
                    <span class="text-muted">Resolution</span>
                    <span class="text-right font-medium">{{ selectedResolutionLabel }}</span>
                  </div>
                  <div class="flex items-center justify-between gap-4">
                    <span class="text-muted">Uploaded</span>
                    <span class="text-right font-medium">{{
                      formatDate(selectedUpload.created_at)
                    }}</span>
                  </div>
                </div>
              </div>

              <div
                v-if="hasMetadata(selectedUpload.meta_data)"
                class="space-y-3 border-t border-default pt-5"
              >
                <div class="flex items-center gap-2 text-sm font-semibold text-highlighted">
                  <UIcon name="i-heroicons-tag-20-solid" class="size-5 text-primary" />
                  <span>Metadata</span>
                </div>
                <div class="space-y-2 text-sm">
                  <div
                    v-for="(val, key) in filterMetadata(selectedUpload.meta_data)"
                    :key="key"
                    class="grid grid-cols-[auto_1fr] gap-2"
                  >
                    <span class="text-muted font-medium capitalize">{{ formatKey(key) }}:</span>
                    <span class="wrap-break-word text-right">{{ formatValue(val) }}</span>
                  </div>
                </div>
              </div>

              <div v-if="playableUploads.length > 1" class="space-y-3 border-t border-default pt-5">
                <div class="flex items-center gap-2 text-sm font-semibold text-highlighted">
                  <UIcon name="i-heroicons-queue-list-20-solid" class="size-5 text-primary" />
                  <span>Available Sources</span>
                </div>
                <div class="space-y-2">
                  <button
                    v-for="upload in playableUploads"
                    :key="upload.public_id"
                    type="button"
                    class="w-full rounded-xl border px-3 py-3 text-left transition-colors"
                    :class="
                      upload.public_id === selectedUpload.public_id
                        ? 'border-primary bg-primary/10 ring-1 ring-primary/30'
                        : 'border-default bg-default hover:bg-elevated/70'
                    "
                    @click="selectedUploadId = upload.public_id"
                  >
                    <div class="flex items-start gap-3">
                      <div
                        class="mt-0.5 flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-default bg-elevated text-primary"
                      >
                        <img
                          v-if="upload.thumbnail_url"
                          :src="upload.thumbnail_url"
                          :alt="`${upload.filename || 'Untitled media'} thumbnail`"
                          class="h-full w-full object-cover"
                        />
                        <UIcon
                          v-else
                          :name="
                            isVideoUpload(upload)
                              ? 'i-heroicons-film-20-solid'
                              : 'i-heroicons-musical-note-20-solid'
                          "
                          class="size-5"
                        />
                      </div>
                      <div class="min-w-0 flex-1 space-y-1">
                        <div class="truncate font-medium text-highlighted">
                          {{ upload.filename || 'Untitled media' }}
                        </div>
                        <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                          <span>{{ upload.mimetype || 'Unknown type' }}</span>
                          <span>{{ formatBytes(upload.size_bytes || 0) || 'Unknown size' }}</span>
                          <span>{{ formatDate(upload.created_at) }}</span>
                        </div>
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </UCard>

      <UAlert
        v-else-if="uploads.length > 0 && !loading && !tokenInfo?.allow_public_downloads"
        color="neutral"
        variant="outline"
        title="Inline playback unavailable"
        description="Public downloads are disabled for this token, so media playback is not available on the share page."
        icon="i-heroicons-lock-closed-20-solid"
      />

      <UAlert
        v-else-if="
          uploads.length > 0 &&
          !loading &&
          tokenInfo?.allow_public_downloads &&
          !playableUploads.length
        "
        color="neutral"
        variant="outline"
        title="No playable media found"
        description="This share contains files, but none of the completed uploads are video or audio."
        icon="i-heroicons-document-20-solid"
      />

      <div v-if="uploads.length > 0" class="space-y-3">
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-folder-open-20-solid" />
          <h2 class="text-lg font-semibold">Files</h2>
        </div>

        <div class="block md:hidden space-y-3">
          <UCard v-for="upload in uploads" :key="upload.public_id">
            <template #header>
              <div class="flex items-start gap-3">
                <UIcon
                  :name="getFileIcon(upload.filename || '')"
                  class="size-6 text-primary shrink-0 mt-0.5"
                />
                <div class="min-w-0 flex-1">
                  <a
                    v-if="
                      tokenInfo?.allow_public_downloads &&
                      upload.status === 'completed' &&
                      upload.download_url
                    "
                    :href="upload.download_url"
                    class="font-medium hover:underline break-all"
                  >
                    {{ upload.filename }}
                  </a>
                  <span v-else class="font-medium break-all">
                    {{ upload.filename }}
                  </span>
                  <div class="flex items-center gap-2 mt-2">
                    <UBadge :color="getStatusColor(upload.status)" variant="soft" size="xs">
                      {{ upload.status }}
                    </UBadge>
                  </div>
                </div>
              </div>
            </template>

            <div class="space-y-3">
              <div class="space-y-2 text-sm">
                <div class="flex items-center justify-between">
                  <span class="text-muted">Size</span>
                  <span class="font-medium">{{ formatBytes(upload.size_bytes || 0) }}</span>
                </div>

                <div class="flex items-center justify-between">
                  <span class="text-muted">Uploaded</span>
                  <span>{{ formatDate(upload.created_at) }}</span>
                </div>

                <div v-if="upload.mimetype" class="flex items-center justify-between">
                  <span class="text-muted">Type</span>
                  <span class="text-xs">{{ upload.mimetype }}</span>
                </div>
              </div>

              <div class="flex gap-2 pt-2 border-t border-default">
                <UPopover :ui="{ content: 'p-3' }">
                  <UButton
                    size="xs"
                    color="neutral"
                    variant="soft"
                    icon="i-heroicons-information-circle-20-solid"
                  >
                    Details
                  </UButton>
                  <template #content>
                    <div class="space-y-3 text-sm min-w-64 max-w-96">
                      <div class="font-semibold text-highlighted">File Details</div>
                      <div class="space-y-2">
                        <div class="grid grid-cols-[auto_1fr] gap-2">
                          <span class="text-muted font-medium">ID:</span>
                          <span>{{ upload.public_id }}</span>
                        </div>
                        <div v-if="upload.mimetype" class="grid grid-cols-[auto_1fr] gap-2">
                          <span class="text-muted font-medium">Type:</span>
                          <span>{{ upload.mimetype }}</span>
                        </div>
                      </div>
                      <div
                        v-if="hasMetadata(upload.meta_data)"
                        class="space-y-2 pt-2 border-t border-default"
                      >
                        <div class="font-semibold text-highlighted">Metadata</div>
                        <div
                          v-for="(val, key) in filterMetadata(upload.meta_data)"
                          :key="key"
                          class="grid grid-cols-[auto_1fr] gap-2"
                        >
                          <span class="text-muted font-medium capitalize"
                            >{{ formatKey(key) }}:</span
                          >
                          <span class="wrap-break-word">{{ formatValue(val) }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                </UPopover>
              </div>
            </div>
          </UCard>
        </div>

        <div class="hidden md:block overflow-x-auto rounded-lg ring ring-default">
          <table class="w-full divide-y divide-default">
            <thead class="bg-elevated">
              <tr>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted min-w-48">
                  Filename
                </th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-32">
                  Status
                </th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-30">
                  Size
                </th>
                <th class="px-4 py-3 text-left text-sm font-semibold text-highlighted w-50">
                  Uploaded
                </th>
              </tr>
            </thead>
            <tbody class="bg-default divide-y divide-default">
              <tr
                v-for="upload in uploads"
                :key="upload.public_id"
                class="hover:bg-elevated/50 transition-colors"
              >
                <td class="px-4 py-3 text-sm">
                  <UPopover mode="hover" :content="{ align: 'start' }" :ui="{ content: 'p-3' }">
                    <div class="flex items-center gap-2">
                      <UIcon
                        :name="getFileIcon(upload.filename || '')"
                        class="size-5 text-primary shrink-0"
                      />
                      <span class="font-medium break-all">
                        <a
                          v-if="
                            tokenInfo?.allow_public_downloads &&
                            upload.status === 'completed' &&
                            upload.download_url
                          "
                          :href="upload.download_url"
                        >
                          {{ upload.filename }}
                        </a>
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
                            <span>{{ upload.public_id }}</span>
                          </div>
                          <div v-if="upload.mimetype" class="grid grid-cols-[auto_1fr] gap-2">
                            <span class="text-muted font-medium">Type:</span>
                            <span>{{ upload.mimetype }}</span>
                          </div>
                        </div>
                        <div
                          v-if="hasMetadata(upload.meta_data)"
                          class="space-y-2 pt-2 border-t border-default"
                        >
                          <div class="font-semibold text-highlighted">Metadata</div>
                          <div
                            v-for="(val, key) in filterMetadata(upload.meta_data)"
                            :key="key"
                            class="grid grid-cols-[auto_1fr] gap-2"
                          >
                            <span class="text-muted font-medium capitalize"
                              >{{ formatKey(key) }}:</span
                            >
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
        <UAlert
          color="neutral"
          variant="outline"
          title="No files available"
          description="There are no uploaded files to display for this token."
          icon="i-heroicons-inbox-20-solid"
        />
      </div>

      <div v-if="loading" class="flex justify-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="size-8 animate-spin text-primary" />
      </div>
    </div>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useStorage } from '@vueuse/core';
import { useRoute } from 'vue-router';
import { useTokenInfo } from '~/composables/useTokenInfo';
import type { UploadRow } from '~/types/uploads';
import { copyText, formatBytes, formatDate, formatKey, formatValue } from '~/utils';

const route = useRoute();
const toast = useToast();
const token = ref<string>((route.params.token as string) || '');

const { tokenInfo, notFound, tokenError, isExpired, isDisabled, fetchTokenInfo } =
  useTokenInfo(token);
const loading = ref(true);
const notice = ref<string>('');
const showNotice = useStorage<boolean>('show_notice', true);
const mediaVolume = useStorage<number>('share_media_volume', 1);
const selectedUploadId = ref<string>('');
const activeUploadId = ref<string>('');
const mediaPlaybackError = ref('');
const mediaElement = ref<HTMLMediaElement | null>(null);

const uploads = computed(
  () => tokenInfo.value?.uploads?.filter((upload) => upload.status === 'completed') || [],
);

const playableUploads = computed(() => {
  return uploads.value.filter((upload) => upload.stream_url && isPlayableUpload(upload));
});

const selectedUpload = computed(() => {
  if (!playableUploads.value.length) return null;
  return (
    playableUploads.value.find((upload) => upload.public_id === selectedUploadId.value) ||
    playableUploads.value[0]
  );
});

const canPlaySelectedMedia = computed(() => {
  return Boolean(tokenInfo.value?.allow_public_downloads && selectedUpload.value?.stream_url);
});

const selectedIsVideo = computed(() => {
  return Boolean(selectedUpload.value && isVideoUpload(selectedUpload.value));
});

const selectedMediaUrl = computed(() => selectedUpload.value?.stream_url || '');
const selectedThumbnailUrl = computed(() => selectedUpload.value?.thumbnail_url || '');
const shouldRenderSelectedMedia = computed(() => {
  return Boolean(selectedUpload.value && activeUploadId.value === selectedUpload.value.public_id);
});

const selectedFfprobe = computed<Record<string, any> | null>(() => {
  const ffprobe = selectedUpload.value?.meta_data?.ffprobe;
  return ffprobe && typeof ffprobe === 'object' ? (ffprobe as Record<string, any>) : null;
});

const selectedDurationLabel = computed(() => {
  const duration = getMediaDurationSeconds(selectedFfprobe.value);
  return duration ? formatDuration(duration) : '';
});

const selectedResolutionLabel = computed(() => {
  const resolution = getVideoResolution(selectedFfprobe.value);
  return resolution ? `${resolution.width} x ${resolution.height}` : '';
});

const shareUrl = computed(() => {
  if (!token.value) return '';
  return `${window.location.origin}/f/${token.value}`;
});

watch(
  playableUploads,
  (nextUploads) => {
    if (!nextUploads.length) {
      selectedUploadId.value = '';
      return;
    }

    const selectedStillExists = nextUploads.some(
      (upload) => upload.public_id === selectedUploadId.value,
    );
    if (!selectedStillExists) {
      const firstUpload = nextUploads[0];
      if (firstUpload) {
        selectedUploadId.value = firstUpload.public_id;
      }
    }
  },
  { immediate: true },
);

watch(
  () => selectedUpload.value?.public_id,
  () => {
    activeUploadId.value = '';
    clearMediaPlaybackError();
  },
);

watch(
  mediaElement,
  (element) => {
    applyStoredMediaVolume(element);
  },
  { immediate: true },
);

watch(
  mediaVolume,
  (nextVolume) => {
    const normalizedVolume = normalizeMediaVolume(nextVolume);
    if (normalizedVolume !== nextVolume) {
      mediaVolume.value = normalizedVolume;
      return;
    }

    applyStoredMediaVolume(mediaElement.value);
  },
  { immediate: true },
);

function copyShareUrl() {
  copyText(shareUrl.value);
  toast.add({
    title: 'Share link copied to clipboard',
    color: 'success',
    icon: 'i-heroicons-check-circle-20-solid',
  });
}

function clearMediaPlaybackError() {
  mediaPlaybackError.value = '';
}

async function activateSelectedMedia() {
  if (!selectedUpload.value) return;
  activeUploadId.value = selectedUpload.value.public_id;
  clearMediaPlaybackError();

  await nextTick();

  try {
    await mediaElement.value?.play();
  } catch {}
}

function handleMediaPlaybackError() {
  mediaPlaybackError.value = selectedIsVideo.value
    ? 'This video could not be played inline in your browser. Download the original file to view it locally.'
    : 'This audio file could not be played inline in your browser. Download the original file to listen locally.';
}

function handleMediaVolumeChange(event: Event) {
  const target = event.target as HTMLMediaElement | null;
  if (!target || typeof target.volume !== 'number') return;

  const normalizedVolume = normalizeMediaVolume(target.volume);
  if (Math.abs(mediaVolume.value - normalizedVolume) > 0.001) {
    mediaVolume.value = normalizedVolume;
  }
}

function applyStoredMediaVolume(element: HTMLMediaElement | null) {
  if (!element) return;

  const normalizedVolume = normalizeMediaVolume(mediaVolume.value);
  if (Math.abs(element.volume - normalizedVolume) > 0.001) {
    element.volume = normalizedVolume;
  }
}

function normalizeMediaVolume(volume: number): number {
  if (!Number.isFinite(volume)) return 1;
  return Math.min(1, Math.max(0, volume));
}

function isPlayableUpload(upload: UploadRow): boolean {
  return Boolean(upload.mimetype?.startsWith('video/') || upload.mimetype?.startsWith('audio/'));
}

function isVideoUpload(upload: UploadRow): boolean {
  return Boolean(upload.mimetype?.startsWith('video/'));
}

function getMediaDurationSeconds(ffprobe: Record<string, any> | null): number | null {
  const duration = ffprobe?.format?.duration;
  if (!duration) return null;
  const parsed = Number(duration);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.round(parsed);
}

function getVideoResolution(
  ffprobe: Record<string, any> | null,
): { width: number; height: number } | null {
  const streams = ffprobe?.streams;
  if (!Array.isArray(streams)) return null;

  const videoStream = streams.find((stream) => stream?.codec_type === 'video');
  const width = Number(videoStream?.width);
  const height = Number(videoStream?.height);

  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }

  return { width, height };
}

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
  }

  return [minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function getStatusColor(status: string): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'error':
    case 'validation_failed':
      return 'error';
    case 'in_progress':
    case 'postprocessing':
    case 'uploading':
      return 'warning';
    default:
      return 'neutral';
  }
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'pdf':
      return 'i-heroicons-document-text-20-solid';
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
    case 'webp':
      return 'i-heroicons-photo-20-solid';
    case 'mp4':
    case 'mov':
    case 'avi':
    case 'mkv':
      return 'i-heroicons-film-20-solid';
    case 'mp3':
    case 'wav':
    case 'flac':
      return 'i-heroicons-musical-note-20-solid';
    case 'zip':
    case 'rar':
    case '7z':
      return 'i-heroicons-archive-box-20-solid';
    case 'doc':
    case 'docx':
      return 'i-heroicons-document-20-solid';
    default:
      return 'i-heroicons-document-20-solid';
  }
}

function filterMetadata(meta_data: Record<string, any> | undefined): Record<string, any> {
  if (!meta_data) return {};
  const { ffprobe, upload_checksums, ...filtered } = meta_data;
  return filtered;
}

function hasMetadata(meta_data: Record<string, any> | undefined): boolean {
  const filtered = filterMetadata(meta_data);
  return Object.keys(filtered).length > 0;
}

onMounted(async () => {
  if (!token.value) {
    notFound.value = true;
    loading.value = false;
    return;
  }

  await fetchTokenInfo();
  loading.value = false;

  try {
    const noticeData = await $fetch<{ notice: string | null }>('/api/notice/');
    if (noticeData.notice) {
      notice.value = noticeData.notice;
    }
  } catch {}
});

useHead({
  title: 'Shared Files',
});
</script>
