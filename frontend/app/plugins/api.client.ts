import { watch } from "vue";

export default defineNuxtPlugin(() => {
  const adminToken = useState<string | null>("adminToken", () => null);

  if (import.meta.client) {
    const stored = localStorage.getItem("adminToken");
    if (stored && !adminToken.value) {
      adminToken.value = stored;
    }

    watch(adminToken, (val) => {
      if (val) {
        localStorage.setItem("adminToken", val);
      } else {
        localStorage.removeItem("adminToken");
      }
    }, { immediate: true });
  }

  const apiFetch = $fetch.create({
    onRequest({ options }) {
      if (adminToken.value) {
        const headers = new Headers(options.headers as HeadersInit);
        headers.set("Authorization", `Bearer ${adminToken.value}`);
        options.headers = headers;
      }
    },
    onResponseError({ response }) {
      if (response.status === 401) {
        adminToken.value = null;
      }
    },
  });

  return { provide: { apiFetch } };
});
