export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return;

  const adminToken = useState<string | null>("adminToken", () => null);
  const lastValidated = useState<number>("adminTokenValidated", () => 0);

  if (import.meta.client && !adminToken.value) {
    const stored = localStorage.getItem("adminToken");
    if (stored) {
      adminToken.value = stored;
    }
  }

  if (!adminToken.value) {
    const redirect = encodeURIComponent(to.fullPath);
    return navigateTo(`/?redirect=${redirect}`);
  }

  // Validate token every 5 minutes
  const now = Date.now();
  const fiveMinutes = 5 * 60 * 1000;

  if (now - lastValidated.value > fiveMinutes) {
    try {
      await $fetch("/api/admin/validate", {
        headers: { Authorization: `Bearer ${adminToken.value}` },
      });
      lastValidated.value = now;
    } catch {
      adminToken.value = null;
      localStorage.removeItem("adminToken");
      const redirect = encodeURIComponent(to.fullPath);
      return navigateTo(`/?redirect=${redirect}`);
    }
  }
});
