/**
 * Copy text to clipboard with optional notification and storage flag.
 *
 * @param str - The string to copy.
 */
const copyText = (str: string): void => {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(str).then(() => { }).catch((e) => {
      console.error('Failed to copy.', e)
    })
    return
  }

  const el = document.createElement('textarea')
  el.value = str
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

/**
 * Format bytes to human-readable string
 */
function formatBytes(size: number): string {
  if (!size) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let s = size;
  let u = 0;
  while (s >= 1024 && u < units.length - 1) {
    s /= 1024;
    u++;
  }
  return `${s.toFixed(1)} ${units[u]}`;
}

/**
 * Format date to locale string with timezone
 */
function formatDate(d?: string) {
  if (!d) return "";
  try {
    const date = new Date(d);
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short'
    });
  } catch {
    return d;
  }
}

/**
 * Calculate percentage from offset and length
 */
function percent(offset?: number, length?: number) {
  if (!length || length <= 0) return "—";
  const val = Math.min(100, Math.round(((offset || 0) / length) * 100));
  return `${val}%`;
}

/**
 * Format metadata key for display
 */
function formatKey(key: string): string {
  return key.replace(/_/g, ' ');
}

/**
 * Format metadata value for display
 */
function formatValue(val: unknown): string {
  if (val === null || val === undefined) return '—';
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

/**
 * Add admin API key to download URL if public downloads are disabled
 */
function addAdminKeyToUrl(url: string, allowPublicDownloads: boolean, apiKey: string | null): string {
  if (allowPublicDownloads || !apiKey) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}api_key=${apiKey}`;
}

export { copyText, formatBytes, formatDate, percent, formatKey, formatValue, addAdminKeyToUrl };