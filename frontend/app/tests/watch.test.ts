import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { useWatchRoom } from '~/composables/useWatchRoom';
import {
  buildWatchSocketUrl,
  driftCorrection,
  expectedWatchPosition,
  isWatchState,
  midpointClockOffset,
} from '~/types/watch';

describe('watch protocol helpers', () => {
  test('uses configured backend socket', () => {
    expect(buildWatchSocketUrl('party-id', 'http://localhost:8000', 'http://localhost:8082')).toBe(
      'ws://localhost:8000/api/watch/party-id/ws',
    );
    expect(
      buildWatchSocketUrl('party-id', 'https://backend.example', 'https://frontend.example'),
    ).toBe('wss://backend.example/api/watch/party-id/ws');
  });

  test('uses production page origin', () => {
    expect(buildWatchSocketUrl('party/id', '', 'https://frontend.example')).toBe(
      'wss://frontend.example/api/watch/party%2Fid/ws',
    );
  });

  test('projects a playing state from the server clock', () => {
    const state = {
      version: 1,
      anchor_position: 10,
      paused: false,
      playback_rate: 2,
      server_time: 100,
      participant_count: 1,
    };
    expect(expectedWatchPosition(state, 102000, 0)).toBe(14);
  });

  test('applies drift correction thresholds', () => {
    expect(driftCorrection(0.1)).toEqual({ seek: null, rate: 1 });
    expect(driftCorrection(0.3).rate).toBe(1.08);
    expect(driftCorrection(-1).seek).toBe(-1);
  });

  test('calculates midpoint clock offset', () => {
    expect(midpointClockOffset(1000, 1200, 1)).toBe(100);
  });

  test('rejects malformed state messages', () => {
    expect(isWatchState({ type: 'state', version: 1 })).toBe(false);
    expect(
      isWatchState({
        version: 1,
        anchor_position: 2,
        paused: true,
        playback_rate: 1,
        server_time: 3,
        participant_count: 2,
      }),
    ).toBe(true);
    expect(
      isWatchState({
        version: 1.5,
        anchor_position: 2,
        paused: true,
        playback_rate: 1,
        server_time: 3,
        participant_count: 2,
      }),
    ).toBe(false);
    expect(
      isWatchState({
        version: 1,
        anchor_position: -1,
        paused: true,
        playback_rate: 1,
        server_time: 3,
        participant_count: 2,
      }),
    ).toBe(false);
  });
});

describe('watch room connection lifecycle', () => {
  const originalSocket = globalThis.WebSocket;
  const originalWindow = globalThis.window;
  let sockets: FakeSocket[];
  let timers: Array<() => void>;
  let sessionValues: Map<string, string>;

  class FakeSocket {
    static readonly OPEN = 1;
    readyState = 0;
    onopen: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    onclose: (() => void) | null = null;
    sent: string[] = [];

    constructor(readonly url: string) {
      sockets.push(this);
    }

    send(message: string) {
      this.sent.push(message);
    }

    close() {
      this.readyState = 3;
      this.onclose?.();
    }

    open() {
      this.readyState = FakeSocket.OPEN;
      this.onopen?.();
    }

    message(message: Record<string, unknown>) {
      this.onmessage?.({ data: JSON.stringify(message) });
    }

    closeUnexpectedly() {
      this.readyState = 3;
      this.onclose?.();
    }
  }

  beforeEach(() => {
    sockets = [];
    timers = [];
    sessionValues = new Map();
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
    globalThis.window = {
      setTimeout: (callback: () => void) => {
        timers.push(callback);
        return timers.length;
      },
      clearTimeout: () => {},
      setInterval: () => 1,
      clearInterval: () => {},
      sessionStorage: {
        getItem: (key: string) => sessionValues.get(key) || null,
        setItem: (key: string, value: string) => sessionValues.set(key, value),
        removeItem: (key: string) => sessionValues.delete(key),
      },
    } as unknown as Window & typeof globalThis;
  });

  afterEach(() => {
    globalThis.WebSocket = originalSocket;
    globalThis.window = originalWindow;
  });

  test('ignores callbacks from stale sockets', () => {
    const room = useWatchRoom();
    room.connect('ws://old', {});
    const oldSocket = sockets[0]!;
    room.connect('ws://current', {});
    const currentSocket = sockets[1]!;

    oldSocket.message({ type: 'error', message: 'Watch Party not found' });
    expect(room.error.value).toBe('');
    currentSocket.open();
    expect(room.status.value).toBe('connecting');
    oldSocket.closeUnexpectedly();
    expect(room.status.value).toBe('connecting');
  });

  test('does not retry a missing room', () => {
    const room = useWatchRoom();
    room.connect('ws://missing', {});
    const socket = sockets[0]!;
    socket.open();
    socket.message({ type: 'error', message: 'Watch Party not found' });

    expect(room.status.value).toBe('error');
    expect(timers).toHaveLength(0);
    expect(sockets).toHaveLength(1);
  });

  test('retries an unexpected close', () => {
    const room = useWatchRoom();
    room.connect('ws://unstable', {});
    sockets[0]!.open();
    sockets[0]!.closeUnexpectedly();
    expect(room.status.value).toBe('reconnecting');

    timers[0]!();
    expect(sockets).toHaveLength(2);
  });

  test('caps retries until ready', () => {
    const room = useWatchRoom();
    room.connect('ws://unstable', {});
    for (let attempt = 0; attempt < 4; attempt += 1) {
      sockets.at(-1)!.closeUnexpectedly();
      timers.at(-1)!();
    }
    sockets.at(-1)!.closeUnexpectedly();
    expect(room.status.value).toBe('error');
    expect(sockets).toHaveLength(5);
  });

  test('falls back from stale host key once', () => {
    const room = useWatchRoom();
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload', host_key: 'old' });
    sockets[0]!.open();
    sockets[0]!.message({
      type: 'ready',
      role: 'host',
      participant_id: 'host-id',
      participant_count: 1,
    });
    sockets[0]!.message({ type: 'error', message: 'Invalid host key' });
    timers.at(-1)!();
    const guestRetry = sockets[1]!;
    guestRetry.open();
    expect(JSON.parse(guestRetry.sent[0]!)).not.toHaveProperty('host_key');
    guestRetry.message({
      type: 'ready',
      role: 'guest',
      participant_id: 'guest-id',
      participant_count: 1,
    });
    guestRetry.message({ type: 'error', message: 'Invalid host key' });
    expect(room.status.value).toBe('error');
    expect(timers).toHaveLength(1);
  });

  test('keeps host media playing', async () => {
    const room = useWatchRoom();
    room.connect('ws://host', { host_key: 'secret' });
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'host',
      participant_id: 'host-id',
      participant_count: 1,
    });
    socket.message({
      type: 'state',
      version: 1,
      anchor_position: 10,
      paused: true,
      playback_rate: 1,
      server_time: Date.now(),
      participant_count: 1,
    });

    const media = {
      currentTime: 10,
      paused: false,
      playbackRate: 1,
      pause() {
        this.paused = true;
      },
      play() {
        this.paused = false;
        return Promise.resolve();
      },
    };

    room.setMedia(media as unknown as HTMLMediaElement);
    await Promise.resolve();
    room.sendPlay();

    expect(media.paused).toBe(false);
    expect(JSON.parse(socket.sent.at(-1)!)).toMatchObject({ type: 'play', position: 10 });
  });

  test('sends selected upload on join', () => {
    const room = useWatchRoom();
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload' });
    const socket = sockets[0]!;
    socket.open();

    expect(JSON.parse(socket.sent[0]!)).toEqual({
      type: 'join',
      download_token: 'token',
      upload_id: 'upload',
    });
  });

  test('uses promoted credential on reconnect', () => {
    const room = useWatchRoom();
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload' });
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'guest',
      participant_id: 'guest-id',
      participant_count: 2,
    });
    socket.message({
      type: 'promotion',
      participant_id: 'guest-id',
      host_key: 'room-credential',
    });
    socket.closeUnexpectedly();

    timers[0]!();
    const reconnect = sockets[1]!;
    reconnect.open();
    expect(JSON.parse(reconnect.sent[0]!)).toMatchObject({
      type: 'join',
      host_key: 'room-credential',
      upload_id: 'upload',
    });
    expect(JSON.parse(reconnect.sent[0]!)).not.toHaveProperty('credential');
  });

  test('stores rotated key for room reloads', () => {
    const room = useWatchRoom();
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload' }, false, 'party');
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'host',
      participant_id: 'host-id',
      participant_count: 1,
      host_key: 'rotated-key',
    });

    const reloaded = useWatchRoom();
    reloaded.connect(
      'ws://party',
      { download_token: 'token', upload_id: 'upload' },
      false,
      'party',
    );
    sockets[1]!.open();
    expect(JSON.parse(sockets[1]!.sent[0]!)).toMatchObject({ host_key: 'rotated-key' });
  });

  test('removes key explicitly', () => {
    const room = useWatchRoom();
    room.storeHostKey('party', 'temporary-key');
    room.removeStoredHostKey('party');
    const reloaded = useWatchRoom();
    reloaded.connect(
      'ws://party',
      { download_token: 'token', upload_id: 'upload' },
      false,
      'party',
    );
    sockets[0]!.open();
    expect(JSON.parse(sockets[0]!.sent[0]!)).not.toHaveProperty('host_key');
  });

  test('falls back to guest after stale stored key', () => {
    const room = useWatchRoom();
    room.storeHostKey('party', 'stale-key');
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload' }, false, 'party');
    sockets[0]!.open();
    sockets[0]!.message({
      type: 'error',
      message: 'Invalid host key',
    });
    timers[0]!();
    sockets[1]!.open();
    expect(JSON.parse(sockets[1]!.sent[0]!)).not.toHaveProperty('host_key');
  });

  test('exposes promotion notice state', () => {
    const room = useWatchRoom();
    room.connect('ws://party', {}, false, 'party');
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'guest',
      participant_id: 'guest-id',
      participant_count: 1,
    });
    expect(room.wasPromoted.value).toBe(false);
    socket.message({ type: 'promotion', participant_id: 'guest-id', host_key: 'new-key' });
    expect(room.wasPromoted.value).toBe(true);
  });

  test('does not let guests send commands', () => {
    const room = useWatchRoom();
    room.connect('ws://party', { download_token: 'token', upload_id: 'upload' });
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'guest',
      participant_id: 'guest-id',
      participant_count: 1,
    });
    room.sendRate(2, 4);
    expect(socket.sent.filter((message) => JSON.parse(message).type === 'rate')).toHaveLength(0);
  });

  test('ignores stale autoplay completion', async () => {
    let resolvePlay!: () => void;
    const firstMedia = {
      currentTime: 0,
      paused: true,
      playbackRate: 1,
      pause() {},
      play: () => new Promise<void>((resolve) => (resolvePlay = resolve)),
    };
    const secondMedia = { ...firstMedia, play: () => Promise.resolve() };
    const room = useWatchRoom();
    room.connect('ws://party', {});
    const socket = sockets[0]!;
    socket.open();
    socket.message({
      type: 'ready',
      role: 'guest',
      participant_id: 'guest-id',
      participant_count: 1,
    });
    room.setMedia(firstMedia as unknown as HTMLMediaElement);
    const state = {
      version: 1,
      anchor_position: 0,
      paused: false,
      playback_rate: 1,
      server_time: Date.now() / 1000,
      participant_count: 1,
    };
    const applying = room.applyState(state, firstMedia as unknown as HTMLMediaElement);
    room.setMedia(secondMedia as unknown as HTMLMediaElement);
    resolvePlay();
    await applying;
    expect(room.autoplayBlocked.value).toBe(false);
  });
});
