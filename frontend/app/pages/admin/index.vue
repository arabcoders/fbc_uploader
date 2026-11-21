<template>
  <UContainer class="space-y-4 py-6 sm:py-8">
    <header class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <h1 class="text-2xl font-semibold tracking-tight text-highlighted">Upload tokens</h1>
      <div class="flex flex-wrap items-center gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-refresh-cw"
          label="Refresh"
          @click="fetchTokens"
          :loading="loadingTokens"
        />
        <UButton icon="i-lucide-plus" label="Create token" @click="openCreate" />
      </div>
    </header>

    <UAlert
      v-if="tokensLoadFailed"
      color="error"
      variant="soft"
      icon="i-lucide-triangle-alert"
      title="Could not load tokens"
      description="Use Refresh to try again."
    />
    <AdminTokensTable
      v-else
      :tokens="tokens"
      :loading="loadingTokens"
      @view-uploads="openUploads"
      @edit="openEdit"
      @delete="askDelete"
    />

    <div
      v-if="totalTokens && !tokensLoadFailed"
      class="flex flex-wrap items-center justify-between gap-3"
    >
      <p class="text-sm tabular-nums text-muted">
        Showing {{ startIndex + 1 }}-{{ endIndex }} of {{ totalTokens }} tokens
      </p>
      <UPagination
        v-if="totalPages > 1"
        v-model:page="currentPage"
        :items-per-page="itemsPerPage"
        :total="totalTokens"
        :sibling-count="0"
        show-edges
        :disabled="loadingTokens"
        size="sm"
        :ui="{ list: 'flex-wrap' }"
      />
    </div>

    <UModal v-model:open="createOpen">
      <template #title>
        <ModalTitle icon="i-lucide-plus" label="Create token" />
      </template>
      <template #body>
        <AdminTokenForm id="create-token-form" @submit="handleCreate" />
      </template>
      <template #footer>
        <UButton
          type="submit"
          form="create-token-form"
          icon="i-lucide-plus"
          label="Create token"
          :loading="creating"
        />
      </template>
    </UModal>

    <UModal v-model:open="editOpen">
      <template #title>
        <ModalTitle icon="i-lucide-pencil" :label="`Edit (${selectedToken?.token})`" />
      </template>
      <template #body>
        <AdminTokenForm
          v-if="selectedToken"
          id="edit-token-form"
          mode="edit"
          :token="selectedToken"
          @submit="handleUpdate"
        />
      </template>
      <template #footer>
        <UButton
          type="submit"
          form="edit-token-form"
          icon="i-lucide-check"
          label="Save changes"
          :loading="savingEdit"
        />
      </template>
    </UModal>

    <UModal v-model:open="uploadsOpen" scrollable :ui="{ content: 'max-w-5xl' }">
      <template #title>
        <ModalTitle icon="i-lucide-folder-open" :label="`Uploads (${uploadsToken?.token})`" />
      </template>
      <template #body>
        <UAlert
          v-if="uploadsLoadFailed"
          color="error"
          variant="soft"
          icon="i-lucide-triangle-alert"
          title="Could not load uploads"
        />
        <AdminUploadsTable
          v-else
          :uploads="uploads"
          :loading="loadingUploads"
          :allow-public-downloads="allowPublicDownloads"
          :admin-token="adminToken"
          @delete="askDeleteUpload"
        />
      </template>
    </UModal>

    <UModal v-model:open="deleteOpen" description="This action cannot be undone.">
      <template #title>
        <ModalTitle icon="i-lucide-triangle-alert" label="Delete token" danger />
      </template>
      <template #body>
        <UCheckbox v-model="deleteFiles" label="Also delete all uploaded files" />
      </template>
      <template #footer>
        <UButton
          color="error"
          icon="i-lucide-trash-2"
          label="Delete token"
          :loading="deleting"
          @click="confirmDelete"
        />
      </template>
    </UModal>

    <UModal v-model:open="deleteUploadOpen" description="This action cannot be undone.">
      <template #title>
        <ModalTitle icon="i-lucide-triangle-alert" label="Delete upload" danger />
      </template>
      <template #body>
        <p class="text-sm">
          Are you sure you want to delete
          <strong class="wrap-anywhere">{{ deleteUploadTarget?.filename }}</strong
          >? This will permanently delete the file.
        </p>
      </template>
      <template #footer>
        <UButton
          color="error"
          icon="i-lucide-trash-2"
          label="Delete"
          :loading="deletingUpload"
          @click="confirmDeleteUpload"
        />
      </template>
    </UModal>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import AdminTokenForm from '~/components/AdminTokenForm.vue';
import AdminTokensTable from '~/components/AdminTokensTable.vue';
import AdminUploadsTable from '~/components/AdminUploadsTable.vue';
import type { AdminToken } from '~/types/token';
import type { UploadRow, ApiError } from '~/types/uploads';

definePageMeta({ middleware: 'admin' });

const { $apiFetch } = useNuxtApp();
const toast = useToast();
const router = useRouter();
const route = useRoute();
const adminToken = useState<string | null>('adminToken', () => null);

const tokens = ref<AdminToken[]>([]);
const loadingTokens = ref(true);
const tokensLoadFailed = ref(false);
const creating = ref(false);
const savingEdit = ref(false);
const deleting = ref(false);
const loadingUploads = ref(false);
const uploadsLoadFailed = ref(false);

const selectedToken = ref<AdminToken | null>(null);
const createOpen = ref(false);
const editOpen = ref(false);

const uploadsOpen = ref(false);
const uploadsToken = ref<AdminToken | null>(null);
const uploads = ref<UploadRow[]>([]);
const allowPublicDownloads = ref(true);

const deleteOpen = ref(false);
const deleteTarget = ref<AdminToken | null>(null);
const deleteFiles = ref(false);

const deleteUploadOpen = ref(false);
const deleteUploadTarget = ref<UploadRow | null>(null);
const deletingUpload = ref(false);

const currentPage = computed({
  get: () => parseInt(String(route.query.page || '1'), 10),
  set: (value: number) => {
    router.push({ query: { ...route.query, page: value } });
  },
});
const itemsPerPage = 10;
const totalTokens = ref(0);

const totalPages = computed(() => Math.ceil(totalTokens.value / itemsPerPage));
const startIndex = computed(() => (currentPage.value - 1) * itemsPerPage);
const endIndex = computed(() => Math.min(startIndex.value + itemsPerPage, totalTokens.value));

const hasAuth = computed(() => Boolean(adminToken.value));

function openCreate(): void {
  createOpen.value = true;
}

async function fetchTokens() {
  if (!hasAuth.value) return;
  loadingTokens.value = true;
  tokensLoadFailed.value = false;
  try {
    const res = await $apiFetch<{ tokens: AdminToken[]; total: number }>('/api/tokens/', {
      query: {
        skip: (currentPage.value - 1) * itemsPerPage,
        limit: itemsPerPage,
      },
    });
    tokens.value = res.tokens;
    totalTokens.value = res.total;
  } catch (err) {
    tokensLoadFailed.value = true;
    handleAuthError(err as ApiError);
  } finally {
    loadingTokens.value = false;
  }
}

async function handleCreate(payload: Record<string, any>) {
  creating.value = true;
  try {
    await $apiFetch('/api/tokens/', { method: 'POST', body: payload });
    toast.add({
      title: 'Token created',
      color: 'success',
      icon: 'i-lucide-circle-check',
    });
    createOpen.value = false;
    await fetchTokens();
  } catch (err) {
    handleAuthError(err as ApiError);
  } finally {
    creating.value = false;
  }
}

function openEdit(token: AdminToken) {
  selectedToken.value = token;
  editOpen.value = true;
}

async function handleUpdate(payload: Record<string, any>) {
  if (!selectedToken.value) return;
  savingEdit.value = true;
  try {
    await $apiFetch(`/api/tokens/${selectedToken.value.token}`, { method: 'PATCH', body: payload });
    toast.add({
      title: 'Token updated',
      color: 'success',
      icon: 'i-lucide-circle-check',
    });
    editOpen.value = false;
    await fetchTokens();
  } catch (err) {
    handleAuthError(err as ApiError);
  } finally {
    savingEdit.value = false;
  }
}

function askDelete(token: AdminToken) {
  deleteTarget.value = token;
  deleteFiles.value = false;
  deleteOpen.value = true;
}

async function confirmDelete() {
  if (!deleteTarget.value) return;
  deleting.value = true;
  try {
    await $apiFetch(`/api/tokens/${deleteTarget.value.token}`, {
      method: 'DELETE',
      query: { delete_files: deleteFiles.value },
    });
    toast.add({
      title: 'Token deleted',
      color: 'success',
      icon: 'i-lucide-circle-check',
    });
    deleteOpen.value = false;
    await fetchTokens();
  } catch (err) {
    handleAuthError(err as ApiError);
  } finally {
    deleting.value = false;
  }
}

async function openUploads(token: AdminToken) {
  uploadsToken.value = token;
  uploadsOpen.value = true;
  loadingUploads.value = true;
  uploadsLoadFailed.value = false;
  try {
    const tokenValue = ref(token.token);
    const { tokenInfo, fetchTokenInfo } = useTokenInfo(tokenValue);
    await fetchTokenInfo();

    if (tokenInfo.value) {
      allowPublicDownloads.value = tokenInfo.value.allow_public_downloads ?? true;
      uploads.value = tokenInfo.value.uploads;
    } else {
      uploadsLoadFailed.value = true;
    }
  } catch (err) {
    uploadsLoadFailed.value = true;
    handleAuthError(err as ApiError);
  } finally {
    loadingUploads.value = false;
  }
}

function askDeleteUpload(upload: UploadRow) {
  deleteUploadTarget.value = upload;
  deleteUploadOpen.value = true;
}

async function confirmDeleteUpload() {
  if (!deleteUploadTarget.value) return;
  deletingUpload.value = true;
  try {
    await $apiFetch(`/api/admin/uploads/${deleteUploadTarget.value.public_id}`, {
      method: 'DELETE',
    });
    toast.add({
      title: 'Upload deleted',
      color: 'success',
      icon: 'i-lucide-circle-check',
    });
    deleteUploadOpen.value = false;
    if (uploadsToken.value) {
      await openUploads(uploadsToken.value);
    }
  } catch (err) {
    handleAuthError(err as ApiError);
  } finally {
    deletingUpload.value = false;
  }
}

function handleAuthError(err: ApiError) {
  if (err?.response?.status === 401 || err?.status === 401) {
    adminToken.value = null;
    toast.add({
      title: 'Session expired',
      description: 'Please sign in again.',
      color: 'error',
      icon: 'i-lucide-triangle-alert',
    });
    navigateTo('/');
  } else {
    toast.add({
      title: 'Request failed',
      description: err?.data?.detail || err?.message || 'No error details were returned.',
      color: 'error',
      icon: 'i-lucide-triangle-alert',
    });
  }
}

watch(
  () => route.query.page,
  () => fetchTokens(),
);
onMounted(() => fetchTokens());
</script>
