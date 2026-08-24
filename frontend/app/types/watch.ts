export type WatchRole = 'host' | 'guest';

export type WatchState = {
  version: number;
  anchor_position: number;
  paused: boolean;
  playback_rate: number;
  server_time: number;
  participant_count: number;
};

export type WatchRoomResponse = {
  room_id: string;
  host_key: string;
  invite_path: string;
};

/** The rotated creator credential delivered in ready/promotion. */
export type WatchCredentialMessage = { host_key?: unknown };

export type WatchStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'error';

export function buildWatchSocketUrl(
  roomId: string,
  configuredBase: string,
  pageOrigin: string,
): string {
  const url = new URL(
    `/api/watch/${encodeURIComponent(roomId)}/ws`,
    configuredBase.trim() || pageOrigin,
  );
  if (url.protocol === 'http:') url.protocol = 'ws:';
  else if (url.protocol === 'https:') url.protocol = 'wss:';
  return url.toString();
}

export function expectedWatchPosition(state: WatchState, now = Date.now(), offset = 0): number {
  if (state.paused) return state.anchor_position;
  return Math.max(
    0,
    state.anchor_position + ((now - offset) / 1000 - state.server_time) * state.playback_rate,
  );
}

export function driftCorrection(drift: number): { seek: number | null; rate: number } {
  const absolute = Math.abs(drift);
  if (absolute >= 0.75) return { seek: drift, rate: 1 };
  if (absolute < 0.15) return { seek: null, rate: 1 };
  return { seek: null, rate: drift > 0 ? 1.08 : 0.92 };
}

export function midpointClockOffset(
  clientTime: number,
  receivedAt: number,
  serverTime: number,
): number {
  return (clientTime + receivedAt) / 2 - serverTime * 1000;
}

export function isWatchState(value: unknown): value is WatchState {
  if (!value || typeof value !== 'object') return false;
  const state = value as Record<string, unknown>;
  return (
    typeof state.version === 'number' &&
    Number.isInteger(state.version) &&
    state.version >= 0 &&
    typeof state.anchor_position === 'number' &&
    Number.isFinite(state.anchor_position) &&
    state.anchor_position >= 0 &&
    state.anchor_position <= 86400 &&
    typeof state.paused === 'boolean' &&
    typeof state.playback_rate === 'number' &&
    Number.isFinite(state.playback_rate) &&
    state.playback_rate >= 0.25 &&
    state.playback_rate <= 4 &&
    typeof state.server_time === 'number' &&
    Number.isFinite(state.server_time) &&
    typeof state.participant_count === 'number' &&
    Number.isInteger(state.participant_count) &&
    state.participant_count >= 0 &&
    state.participant_count <= 32
  );
}
