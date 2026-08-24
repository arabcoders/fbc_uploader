import { computed, getCurrentInstance, onBeforeUnmount, ref } from 'vue';
import type {
  WatchCredentialMessage,
  WatchRole,
  WatchRoomResponse,
  WatchState,
  WatchHostStatus,
  WatchStatus,
} from '~/types/watch';
import {
  driftCorrection,
  expectedWatchPosition,
  isWatchState,
  midpointClockOffset,
} from '~/types/watch';

export type WatchMedia = HTMLMediaElement;

export function useWatchRoom() {
  const status = ref<WatchStatus>('idle');
  const role = ref<WatchRole | null>(null);
  const participantCount = ref(0);
  const state = ref<WatchState | null>(null);
  const error = ref('');
  const autoplayBlocked = ref(false);
  const wasPromoted = ref(false);
  const hostWaiting = ref(false);
  const room = ref<WatchRoomResponse | null>(null);
  const clockOffset = ref(0);
  let socket: WebSocket | null = null;
  let reconnectTimer = 0;
  let pingTimer = 0;
  let snapshotTimer = 0;
  let correctionTimer = 0;
  let media: WatchMedia | null = null;
  let roomUrl = '';
  let joinMessage: Record<string, string> | null = null;
  let reconnectCredential = '';
  let participantId = '';
  let reconnectAttempts = 0;
  let hostFallbackUsed = false;
  let deliberateClose = false;
  let fatalClose = false;
  let suppressedUntil = 0;
  let mediaGeneration = 0;
  let applyGeneration = 0;
  let roomId = '';
  let syncRequired = false;
  let readyReceived = false;
  let hostStatusVersion = -1;
  let requiredSyncVersion = 0;
  let syncSentVersion = -1;
  let participantVersion = -1;

  const isHost = computed(() => role.value === 'host');
  const invitePath = computed(() => room.value?.invite_path || '');

  function storageKey(id: string) {
    return `watch-host-key:${id}`;
  }

  function storedHostKey(id: string): string {
    if (typeof window === 'undefined' || !id) return '';
    try {
      return window.sessionStorage.getItem(storageKey(id)) || '';
    } catch {
      return '';
    }
  }

  function storeHostKey(id: string, key: string) {
    if (typeof window === 'undefined' || !id || !key) return;
    try {
      window.sessionStorage.setItem(storageKey(id), key);
    } catch {}
  }

  function removeStoredHostKey(id: string) {
    if (typeof window === 'undefined' || !id) return;
    try {
      window.sessionStorage.removeItem(storageKey(id));
    } catch {}
  }

  function connect(url: string, message: Record<string, string>, reconnect = false, id = '') {
    if (typeof window === 'undefined') return;
    deliberateClose = false;
    fatalClose = false;
    roomUrl = url;
    joinMessage = { ...message };
    roomId = id || roomIdFromUrl(url) || roomId;
    if (!reconnect) wasPromoted.value = false;
    hostWaiting.value = false;
    syncRequired = false;
    readyReceived = false;
    hostStatusVersion = -1;
    requiredSyncVersion = 0;
    syncSentVersion = -1;
    participantVersion = -1;
    if (!joinMessage.host_key) {
      const stored = storedHostKey(roomId);
      if (stored) joinMessage.host_key = stored;
    }
    if (!reconnect) hostFallbackUsed = false;
    status.value = reconnect ? 'reconnecting' : 'connecting';
    const previousSocket = socket;
    socket = null;
    previousSocket?.close();
    const currentSocket = new WebSocket(url);
    socket = currentSocket;
    currentSocket.onopen = () => {
      if (socket !== currentSocket) return;
      currentSocket.send(JSON.stringify({ type: 'join', ...buildJoinMessage() }));
      startTimers(currentSocket);
    };
    currentSocket.onmessage = (event) => {
      if (socket !== currentSocket) return;
      let message: unknown;
      try {
        message = JSON.parse(event.data);
      } catch {
        setError('Invalid server message', false, currentSocket);
        return;
      }
      if (message && typeof message === 'object')
        handleMessage(message as Record<string, unknown>, currentSocket);
      else setError('Invalid server message', false, currentSocket);
    };
    currentSocket.onerror = () => {
      if (socket !== currentSocket) return;
      if (!fatalClose) error.value = 'Watch Party connection failed';
    };
    currentSocket.onclose = () => {
      if (socket !== currentSocket) return;
      stopTimers();
      if (!deliberateClose && !fatalClose && reconnectAttempts < 4) {
        status.value = 'reconnecting';
        const delay = Math.min(8000, 750 * 2 ** reconnectAttempts++);
        reconnectTimer = window.setTimeout(() => {
          if (socket === currentSocket && !fatalClose)
            connect(roomUrl, joinMessage || {}, true, roomId);
        }, delay);
      } else if (!deliberateClose && !fatalClose) status.value = 'error';
    };
  }

  function startTimers(currentSocket: WebSocket) {
    stopTimers();
    pingTimer = window.setInterval(
      () => send({ type: 'ping', client_time: Date.now() }, currentSocket),
      10000,
    );
    snapshotTimer = window.setInterval(() => {
      if (socket === currentSocket && readyReceived && isHost.value && !syncRequired)
        sendSnapshot(currentSocket);
    }, 1000);
  }

  function stopTimers() {
    window.clearTimeout(reconnectTimer);
    window.clearInterval(pingTimer);
    window.clearInterval(snapshotTimer);
  }

  function setError(message: string, fatal = false, currentSocket: WebSocket | null = socket) {
    error.value = message;
    fatalClose = fatal;
    if (fatal) {
      stopTimers();
      window.clearTimeout(reconnectTimer);
      status.value = 'error';
      hostWaiting.value = false;
      if (socket === currentSocket) currentSocket?.close(1008);
    }
  }

  function buildJoinMessage(): Record<string, string> {
    const message = { ...(joinMessage || {}) };
    if (reconnectCredential) {
      message.host_key = reconnectCredential;
    }
    return message;
  }

  function rememberCredential(message: WatchCredentialMessage) {
    if (typeof message.host_key === 'string' && message.host_key.length > 0) {
      reconnectCredential = message.host_key;
      storeHostKey(roomId, message.host_key);
    }
  }

  function roomIdFromUrl(url: string) {
    const match = url.match(/\/api\/watch\/([^/]+)\/ws/);
    return match ? decodeURIComponent(match[1] || '') : '';
  }

  function handleMessage(message: Record<string, unknown>, currentSocket: WebSocket = socket!) {
    const type = message.type;
    if (
      type === 'ready' &&
      (message.role === 'host' || message.role === 'guest') &&
      typeof message.participant_id === 'string' &&
      isParticipantCount(message.participant_count)
    ) {
      rememberCredential(message);
      participantId = message.participant_id;
      role.value = message.role;
      syncRequired = message.sync_required === true;
      requiredSyncVersion = syncRequired
        ? isVersion(message.version)
          ? message.version
          : (state.value?.version ?? 0) + 1
        : 0;
      syncSentVersion = -1;
      readyReceived = true;
      status.value = 'connected';
      error.value = '';
      reconnectAttempts = 0;
      updateParticipantCount(message.participant_count, message.participant_version);
      send({ type: 'ping', client_time: Date.now() }, currentSocket);
      if (message.role === 'host' && !syncRequired) sendSnapshot(currentSocket);
    } else if (type === 'state' && isWatchState(message)) {
      if (!state.value || message.version >= state.value.version) {
        state.value = message;
        updateParticipantCount(message.participant_count, message.participant_version);
        hostStatusVersion = Math.max(hostStatusVersion, message.version);
      }
      if (!isHost.value || syncRequired) {
        void applyLatest();
      }
    } else if (
      type === 'synced' &&
      isVersion(message.version) &&
      message.version >= requiredSyncVersion
    ) {
      syncRequired = false;
      syncSentVersion = -1;
      error.value = '';
    } else if (
      type === 'host_status' &&
      isWatchHostStatus(message.status) &&
      typeof message.version === 'number' &&
      Number.isInteger(message.version) &&
      message.version >= hostStatusVersion
    ) {
      hostStatusVersion = message.version;
      hostWaiting.value = message.status === 'waiting';
    } else if (type === 'participants' && isParticipantCount(message.participant_count)) {
      updateParticipantCount(message.participant_count, message.participant_version);
    } else if (
      type === 'pong' &&
      typeof message.client_time === 'number' &&
      typeof message.server_time === 'number'
    ) {
      const sample = midpointClockOffset(message.client_time, Date.now(), message.server_time);
      clockOffset.value = clockOffset.value ? clockOffset.value * 0.8 + sample * 0.2 : sample;
    } else if (type === 'promotion' && message.participant_id === participantId) {
      rememberCredential(message);
      wasPromoted.value = true;
      role.value = 'host';
      syncRequired = true;
      requiredSyncVersion = isVersion(message.version)
        ? message.version
        : (state.value?.version ?? 0) + 1;
      syncSentVersion = -1;
      window.clearTimeout(correctionTimer);
    } else if (type === 'error' && typeof message.message === 'string') {
      const normalized = message.message.toLowerCase();
      const hasHostCredential = Boolean(reconnectCredential || joinMessage?.host_key);
      if (normalized.includes('host key') && hasHostCredential && !hostFallbackUsed) {
        hostFallbackUsed = true;
        reconnectCredential = '';
        if (joinMessage) delete joinMessage.host_key;
        removeStoredHostKey(roomId);
        fatalClose = false;
        currentSocket.close(1008);
        return;
      }
      setError(
        message.message,
        normalized.includes('host key') ||
          normalized.includes('credential') ||
          normalized.includes('upload') ||
          normalized.includes('full') ||
          normalized.includes('room') ||
          normalized.includes('not found'),
        currentSocket,
      );
      if (fatalClose) deliberateClose = true;
    }
  }

  function isParticipantCount(value: unknown): value is number {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 32;
  }

  function isVersion(value: unknown): value is number {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0;
  }

  function updateParticipantCount(count: unknown, version: unknown) {
    if (!isParticipantCount(count)) return;
    if (isVersion(version)) {
      if (version < participantVersion) return;
      participantVersion = version;
    } else if (participantVersion >= 0) return;
    participantCount.value = count;
  }

  function isWatchHostStatus(value: unknown): value is WatchHostStatus {
    return value === 'waiting' || value === 'connected';
  }

  function send(message: Record<string, unknown>, targetSocket: WebSocket | null = socket) {
    if (targetSocket && socket === targetSocket && targetSocket.readyState === WebSocket.OPEN)
      targetSocket.send(JSON.stringify(message));
  }
  function currentPosition() {
    return media?.currentTime || 0;
  }
  function sendPlay() {
    if (canControl()) send({ type: 'play', position: currentPosition() });
  }
  function sendPause() {
    if (canControl()) send({ type: 'pause', position: currentPosition() });
  }
  function sendSeek(position = currentPosition()) {
    if (canControl()) send({ type: 'seek', position });
  }
  function sendRate(playback_rate = media?.playbackRate || 1, position = currentPosition()) {
    if (canControl()) send({ type: 'rate', position, playback_rate });
  }
  function sendSnapshot(targetSocket: WebSocket | null = socket) {
    if (canControl() && media)
      send(
        {
          type: 'snapshot',
          position: media.currentTime,
          paused: media.paused,
          playback_rate: media.playbackRate,
        },
        targetSocket,
      );
  }
  function canControl() {
    return isHost.value && readyReceived && !syncRequired && !isSuppressed();
  }
  function isSuppressed() {
    return Date.now() < suppressedUntil;
  }

  async function applyState(next: WatchState, target: WatchMedia) {
    media = target;
    const generation = ++applyGeneration;
    const targetGeneration = mediaGeneration;
    suppressedUntil = Date.now() + 500;
    const expected = expectedWatchPosition(next, Date.now(), clockOffset.value);
    const correction = driftCorrection(expected - target.currentTime);
    if (correction.seek !== null) target.currentTime = expected;
    if (correction.rate !== 1) {
      target.playbackRate = next.playback_rate * correction.rate;
      window.clearTimeout(correctionTimer);
      correctionTimer = window.setTimeout(() => {
        if (
          media === target &&
          mediaGeneration === targetGeneration &&
          applyGeneration === generation
        ) {
          suppressedUntil = Date.now() + 250;
          target.playbackRate = next.playback_rate;
        }
      }, 1200);
    } else target.playbackRate = next.playback_rate;
    if (next.paused && !target.paused) target.pause();
    if (!next.paused && target.paused) {
      try {
        await target.play();
        if (
          media === target &&
          mediaGeneration === targetGeneration &&
          applyGeneration === generation &&
          !isHost.value
        ) {
          autoplayBlocked.value = false;
        }
      } catch {
        if (
          media === target &&
          mediaGeneration === targetGeneration &&
          applyGeneration === generation &&
          !isHost.value
        ) {
          autoplayBlocked.value = true;
        }
      }
    }
  }

  async function applyLatest() {
    if (
      (!isHost.value || syncRequired) &&
      state.value &&
      media &&
      (!syncRequired || state.value.version >= requiredSyncVersion)
    ) {
      await applyState(state.value, media);
      if (syncRequired && syncSentVersion !== state.value.version) {
        syncSentVersion = state.value.version;
        send({ type: 'synced', version: state.value.version });
      }
    }
  }
  function setMedia(next: WatchMedia | null) {
    if (media !== next) {
      mediaGeneration += 1;
      applyGeneration += 1;
      window.clearTimeout(correctionTimer);
    }
    media = next;
    if (!isHost.value || syncRequired) void applyLatest();
  }
  function disconnect() {
    deliberateClose = true;
    stopTimers();
    window.clearTimeout(correctionTimer);
    mediaGeneration += 1;
    applyGeneration += 1;
    socket?.close(1000);
    socket = null;
    media = null;
    joinMessage = null;
    reconnectCredential = '';
    roomUrl = '';
    roomId = '';
    participantId = '';
    reconnectAttempts = 0;
    hostFallbackUsed = false;
    status.value = 'idle';
    role.value = null;
    participantCount.value = 0;
    state.value = null;
    error.value = '';
    autoplayBlocked.value = false;
    clockOffset.value = 0;
    room.value = null;
    wasPromoted.value = false;
    hostWaiting.value = false;
    syncRequired = false;
    readyReceived = false;
    hostStatusVersion = -1;
    requiredSyncVersion = 0;
    syncSentVersion = -1;
    participantVersion = -1;
  }
  if (getCurrentInstance()) onBeforeUnmount(disconnect);
  return {
    status,
    role,
    isHost,
    participantCount,
    state,
    error,
    autoplayBlocked,
    wasPromoted,
    hostWaiting,
    room,
    invitePath,
    clockOffset,
    connect,
    send,
    sendPlay,
    sendPause,
    sendSeek,
    sendRate,
    buildJoinMessage,
    sendSnapshot,
    applyState,
    setMedia,
    applyLatest,
    isSuppressed,
    disconnect,
    storeHostKey,
    removeStoredHostKey,
  };
}
