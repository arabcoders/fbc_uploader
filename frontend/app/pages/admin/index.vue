<template>
  <UContainer class="py-10 space-y-8">
    <div class="flex flex-wrap items-center justify-between gap-4 pb-1">
      <div>
        <h1 class="text-3xl font-bold">Admin panel</h1>
        <p class="text-muted mt-1">Manage upload tokens</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton color="neutral" variant="ghost" icon="i-heroicons-arrow-path" @click="fetchTokens"
          :loading="loadingTokens">
          Refresh
        </UButton>
      </div>
    </div>

    <UCard variant="outline">
      <template #header>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-rectangle-group-20-solid" class="size-5" />
            <span class="font-semibold">Tokens</span>
            <UBadge color="primary" variant="soft">{{ totalTokens }}</UBadge>
          </div>
          <UButton color="primary" icon="i-heroicons-plus-20-solid" @click="createOpen = true">
            Create token
          </UButton>
        </div>
      </template>

      <AdminTokensTable :tokens="tokens" :loading="loadingTokens" @view-uploads="openUploads" @edit="openEdit"
        @delete="askDelete" />

      <template #footer>
        <div class="flex items-center justify-between px-4 py-3">
          <div class="text-sm text-muted">
            <template v-if="totalTokens">
              Showing {{ startIndex + 1 }}-{{ endIndex }} of {{ totalTokens }} tokens
            </template>
            <template v-else>&nbsp;</template>
          </div>
          <div class="flex items-center gap-2">
            <UButton color="neutral" variant="ghost" icon="i-heroicons-chevron-left-20-solid"
              :disabled="currentPage === 1 || !totalPages" @click="currentPage--" />
            <div class="text-sm font-medium">
              {{ currentPage }} / {{ totalPages }}
            </div>
            <UButton color="neutral" variant="ghost" icon="i-heroicons-chevron-right-20-solid"
              :disabled="currentPage === totalPages || !totalPages" @click="currentPage++" />
          </div>
        </div>
      </template>
    </UCard>

    <UModal v-model:open="createOpen" title="Create token">
      <template #body>
        <AdminTokenForm :loading="creating" @submit="handleCreate" />
      </template>
    </UModal>

    <UModal v-model:open="editOpen" title="Edit token">
      <template #body>
        <div v-if="selectedToken" class="space-y-4">
          <div class="text-sm">
            <div class="font-semibold">Token</div>
            <code
              class="font-mono text-xs bg-elevated px-2 py-1 rounded mt-1 inline-block">{{ selectedToken.token }}</code>
          </div>
          <AdminTokenForm mode="edit" :token="selectedToken" :loading="savingEdit" submit-label="Save changes"
            @submit="handleUpdate" />
        </div>
      </template>
    </UModal>

    <UModal v-model:open="uploadsOpen" title="Uploads" scrollable :ui="{ content: 'max-w-5xl' }">
      <template #body>
        <div class="space-y-3">
          <div v-if="uploadsToken" class="text-sm">
            <div class="font-semibold">Token</div>
            <code
              class="font-mono text-xs bg-elevated px-2 py-1 rounded mt-1 inline-block">{{ uploadsToken.token }}</code>
          </div>
          <AdminUploadsTable :uploads="uploads" :loading="loadingUploads" @delete="askDeleteUpload" />
        </div>
      </template>
    </UModal>

    <UModal v-model:open="deleteOpen">
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-exclamation-triangle-20-solid" class="size-5 text-error" />
          <span class="font-semibold">Delete token</span>
        </div>
      </template>
      <template #body>
        <div class="space-y-4">
          <p class="text-sm">
            Are you sure you want to delete this token? This action cannot be undone.
          </p>
          <UCheckbox v-model="deleteFiles" label="Also delete all uploaded files" />
        </div>
      </template>
      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="deleteOpen = false">Cancel</UButton>
          <UButton color="error" :loading="deleting" @click="confirmDelete">Delete token</UButton>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="deleteUploadOpen">
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-exclamation-triangle-20-solid" class="size-5 text-error" />
          <span class="font-semibold">Delete upload</span>
        </div>
      </template>
      <template #body>
        <p class="text-sm">
          Are you sure you want to delete <strong>{{ deleteUploadTarget?.filename }}</strong>? This will permanently
          delete the file.
        </p>
      </template>
      <template #footer>
        <div class="flex items-center justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="deleteUploadOpen = false">Cancel</UButton>
          <UButton color="error" :loading="deletingUpload" @click="confirmDeleteUpload">Delete</UButton>
        </div>
      </template>
    </UModal>
  </UContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AdminTokenForm from "~/components/AdminTokenForm.vue";
import AdminTokensTable from "~/components/AdminTokensTable.vue";
import AdminUploadsTable from "~/components/AdminUploadsTable.vue";
import type { AdminToken } from "~/types/token";
import type { UploadRow } from "~/types/uploads";

definePageMeta({ middleware: "admin" });

const { $apiFetch } = useNuxtApp();
const toast = useToast();
const router = useRouter();
const route = useRoute();
const adminToken = useState<string | null>("adminToken", () => null);

const tokens = ref<AdminToken[]>([]);
const loadingTokens = ref(false);
const creating = ref(false);
const savingEdit = ref(false);
const deleting = ref(false);
const loadingUploads = ref(false);

const selectedToken = ref<AdminToken | null>(null);
const createOpen = ref(false);
const editOpen = ref(false);

const uploadsOpen = ref(false);
const uploadsToken = ref<AdminToken | null>(null);
const uploads = ref<UploadRow[]>([]);

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

async function fetchTokens() {
  if (!hasAuth.value) return;
  loadingTokens.value = true;
  try {
    const res = await $apiFetch<{ tokens: AdminToken[]; total: number }>("/api/tokens/", {
      query: {
        skip: (currentPage.value - 1) * itemsPerPage,
        limit: itemsPerPage,
      },
    });
    tokens.value = res.tokens;
    totalTokens.value = res.total;
  } catch (err: any) {
    handleAuthError(err);
  } finally {
    loadingTokens.value = false;
  }
}

async function handleCreate(payload: Record<string, any>) {
  creating.value = true;
  try {
    await $apiFetch("/api/tokens/", { method: "POST", body: payload });
    toast.add({ title: "Token created", color: "success", icon: "i-heroicons-check-circle-20-solid" });
    createOpen.value = false;
    await fetchTokens();
  } catch (err: any) {
    handleAuthError(err);
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
    await $apiFetch(`/api/tokens/${selectedToken.value.token}`, { method: "PATCH", body: payload });
    toast.add({ title: "Token updated", color: "success", icon: "i-heroicons-check-circle-20-solid" });
    editOpen.value = false;
    await fetchTokens();
  } catch (err: any) {
    handleAuthError(err);
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
      method: "DELETE",
      query: { delete_files: deleteFiles.value },
    });
    toast.add({ title: "Token deleted", color: "success", icon: "i-heroicons-check-circle-20-solid" });
    deleteOpen.value = false;
    await fetchTokens();
  } catch (err: any) {
    handleAuthError(err);
  } finally {
    deleting.value = false;
  }
}

async function openUploads(token: AdminToken) {
  uploadsToken.value = token;
  uploadsOpen.value = true;
  loadingUploads.value = true;
  try {
    const res = await $apiFetch<UploadRow[]>(`/api/tokens/${token.token}/uploads`);
    uploads.value = res;
  } catch (err: any) {
    handleAuthError(err);
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
    await $apiFetch(`/api/admin/uploads/${deleteUploadTarget.value.id}`, { method: "DELETE" });
    toast.add({ title: "Upload deleted", color: "success", icon: "i-heroicons-check-circle-20-solid" });
    deleteUploadOpen.value = false;
    // Refresh the uploads list
    if (uploadsToken.value) {
      await openUploads(uploadsToken.value);
    }
  } catch (err: any) {
    handleAuthError(err);
  } finally {
    deletingUpload.value = false;
  }
}

function handleAuthError(err: any) {
  if (err?.response?.status === 401 || err?.status === 401) {
    adminToken.value = null;
    toast.add({
      title: "Session expired",
      description: "Please sign in again.",
      color: "error",
      icon: "i-heroicons-exclamation-triangle-20-solid",
    });
    navigateTo("/")
  } else {
    toast.add({
      title: "Request failed",
      description: err?.data?.detail || err?.message || "Unexpected error",
      color: "error",
      icon: "i-heroicons-exclamation-triangle-20-solid",
    });
  }
}

watch(() => route.query.page, () => fetchTokens());
onMounted(() => fetchTokens());
</script>
