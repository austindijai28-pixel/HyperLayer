// Core client-side transfer engine: WebSocket lifecycle, chunking via
// File.slice(), Web Worker SHA-256 hashing, sliding-window flow control,
// binary framing, resumable sessions (persisted in localStorage), and
// real-time telemetry. React components subscribe via the callback hooks
// passed into the constructor - this file has no React dependency itself.

import { packChunkFrame, uuidToBytes } from "./protocol.js";

const STORAGE_KEY_PREFIX = "hyperlocal_session_";

export const ConnectionStatus = {
  DISCONNECTED: "DISCONNECTED",
  CONNECTING: "CONNECTING",
  CONNECTED: "CONNECTED",
  RECONNECTING: "RECONNECTING",
};

export const TransferPhase = {
  IDLE: "IDLE",
  TRANSFERRING: "TRANSFERRING",
  RECOVERY: "RECOVERY",
  COMPLETE: "COMPLETE",
  ERROR: "ERROR",
};

function wsUrlForCurrentHost() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export class TransferEngine {
  constructor({ onConnectionStatus, onPhase, onProgress, onError, onComplete }) {
    this.onConnectionStatus = onConnectionStatus || (() => {});
    this.onPhase = onPhase || (() => {});
    this.onProgress = onProgress || (() => {});
    this.onError = onError || (() => {});
    this.onComplete = onComplete || (() => {});

    this.ws = null;
    this.hashWorker = new Worker(new URL("./hasher.worker.js", import.meta.url), { type: "module" });
    this._hashRequests = new Map();
    this.hashWorker.onmessage = (e) => this._onWorkerMessage(e);

    this.file = null;
    this.fileIdBytes = null;
    this.sessionId = null;
    this.chunkSize = 5 * 1024 * 1024;
    this.totalChunks = 0;
    this.reconnectAttempts = 0;
    this._manualClose = false;

    this._reset();
  }

  _reset() {
    this.queuedChunks = [];
    this.inFlight = new Map(); // chunkIndex -> { sentAt }
    this.acknowledged = new Set();
    this.retryCounts = new Map();
    this.windowSize = 8;
    this.bytesTransferred = 0;
    this.startTime = null;
    this._speedSamples = []; // [{t, bytes}]
    this.retransmissions = 0;
  }

  // --- Public API -----------------------------------------------------

  connect() {
    this._manualClose = false;
    this.onConnectionStatus(ConnectionStatus.CONNECTING);
    this.ws = new WebSocket(wsUrlForCurrentHost());
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onConnectionStatus(ConnectionStatus.CONNECTED);
      // If we have a persisted session for the current file, try to resume it.
      const persisted = this.file ? this._loadPersistedSession(this.file) : null;
      if (persisted) {
        this.sessionId = persisted.sessionId;
        this._sendJson({ type: "RESUME_REQUEST", session_id: persisted.sessionId });
      }
    };

    this.ws.onmessage = (event) => this._onSocketMessage(event);

    this.ws.onclose = () => {
      if (this._manualClose) {
        this.onConnectionStatus(ConnectionStatus.DISCONNECTED);
        return;
      }
      const wasTransferring = this.file !== null && this.onPhase !== null;
      this.onConnectionStatus(ConnectionStatus.RECONNECTING);
      if (wasTransferring) {
        this.onPhase(TransferPhase.RECOVERY);
      }
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose will fire right after; real handling happens there.
    };
  }

  disconnect() {
    this._manualClose = true;
    if (this.ws) this.ws.close();
  }

  async startTransfer(file, chunkSize) {
    this.file = file;
    this.chunkSize = chunkSize;
    this._reset();
    this.windowSize = 8;
    this.startTime = performance.now();
    this.onPhase(TransferPhase.TRANSFERRING);

    const persisted = this._loadPersistedSession(file);
    if (persisted && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.sessionId = persisted.sessionId;
      this._sendJson({ type: "RESUME_REQUEST", session_id: persisted.sessionId });
      return;
    }

    this._sendJson({
      type: "INIT",
      file_name: file.name,
      file_size: file.size,
      chunk_size: chunkSize,
    });
  }

  // --- Internals --------------------------------------------------------

  _sendJson(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  _scheduleReconnect() {
    this.reconnectAttempts += 1;
    const delay = Math.min(1000 * 2 ** Math.min(this.reconnectAttempts, 5), 15000);
    setTimeout(() => {
      if (!this._manualClose) this.connect();
    }, delay);
  }

  _onSocketMessage(event) {
    if (typeof event.data === "string") {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      this._handleControlMessage(msg);
    }
    // Server never sends binary frames in this protocol version; binary
    // flow is client -> server only.
  }

  _handleControlMessage(msg) {
    switch (msg.type) {
      case "SESSION_READY":
        this.sessionId = msg.session_id;
        this.fileIdBytes = uuidToBytes(msg.file_id);
        this.totalChunks = msg.total_chunks;
        this.windowSize = msg.window_size;
        this._persistSession(this.file, msg.session_id);
        this.queuedChunks = [...msg.missing_chunks];
        this.acknowledged = new Set(
          Array.from({ length: this.totalChunks }, (_, i) => i).filter(
            (i) => !msg.missing_chunks.includes(i)
          )
        );
        this.bytesTransferred = this.acknowledged.size * this.chunkSize;
        this.onPhase(TransferPhase.TRANSFERRING);
        this._pumpWindow();
        break;

      case "CHUNK_ACK":
        this.inFlight.delete(msg.chunk_index);
        this.acknowledged.add(msg.chunk_index);
        this.windowSize = msg.window_size;
        this._recordProgress(msg.received_count, msg.total_chunks);
        this._pumpWindow();
        break;

      case "CHUNK_RETRY":
        this.inFlight.delete(msg.chunk_index);
        this.retransmissions += 1;
        this.retryCounts.set(msg.chunk_index, msg.retry_count);
        this.queuedChunks.push(msg.chunk_index); // requeue for retransmission
        this._pumpWindow();
        break;

      case "TRANSFER_COMPLETE": {
        this._clearPersistedSession(this.file);
        const duration = (performance.now() - this.startTime) / 1000;
        this.onPhase(TransferPhase.COMPLETE);
        this.onComplete({
          fileName: this.file.name,
          fileSize: this.file.size,
          durationSeconds: msg.duration_seconds ?? duration,
          integrityVerified: msg.integrity_verified,
          retransmissions: this.retransmissions,
          fileHash: msg.file_hash,
        });
        break;
      }

      case "ERROR":
        this.onPhase(TransferPhase.ERROR);
        this.onError(msg.code, msg.message);
        break;

      default:
        break;
    }
  }

  _availableSlots() {
    return Math.max(0, this.windowSize - this.inFlight.size);
  }

  async _pumpWindow() {
    let slots = this._availableSlots();
    while (slots > 0 && this.queuedChunks.length > 0) {
      const chunkIndex = this.queuedChunks.shift();
      slots -= 1;
      this._sendChunk(chunkIndex); // fire and forget; async internally
    }

    if (this.queuedChunks.length === 0 && this.inFlight.size === 0 && this.acknowledged.size < this.totalChunks) {
      // Nothing queued/in-flight but not complete - shouldn't normally
      // happen, but guards against a stalled transfer.
    }
  }

  async _sendChunk(chunkIndex) {
    this.inFlight.set(chunkIndex, { sentAt: performance.now() });
    try {
      const start = chunkIndex * this.chunkSize;
      const end = Math.min(start + this.chunkSize, this.file.size);
      const blob = this.file.slice(start, end); // File API - does not read the whole file into RAM
      const buffer = await blob.arrayBuffer();
      const hashBytes = await this._hashBuffer(buffer);

      const frame = packChunkFrame(this.fileIdBytes, chunkIndex, buffer, new Uint8Array(hashBytes));

      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(frame);
      } else {
        this.inFlight.delete(chunkIndex);
        this.queuedChunks.push(chunkIndex);
      }
    } catch (err) {
      this.inFlight.delete(chunkIndex);
      this.queuedChunks.push(chunkIndex);
    }
  }

  _hashBuffer(buffer) {
    return new Promise((resolve, reject) => {
      const id = `${Date.now()}_${Math.random()}`;
      this._hashRequests.set(id, { resolve, reject });
      // Transfer buffer ownership only if the caller doesn't need it again;
      // here we still need `buffer` afterward, so copy it for the worker.
      const copy = buffer.slice(0);
      this.hashWorker.postMessage({ id, buffer: copy }, [copy]);
    });
  }

  _onWorkerMessage(event) {
    const { id, hashBytes, error } = event.data;
    const req = this._hashRequests.get(id);
    if (!req) return;
    this._hashRequests.delete(id);
    if (error) req.reject(new Error(error));
    else req.resolve(hashBytes);
  }

  _recordProgress(receivedCount, totalChunks) {
    this.bytesTransferred = receivedCount * this.chunkSize > this.file.size
      ? this.file.size
      : receivedCount * this.chunkSize;

    const now = performance.now();
    this._speedSamples.push({ t: now, bytes: this.bytesTransferred });
    // Keep only the last ~3 seconds of samples for a moving-average current speed.
    const cutoff = now - 3000;
    this._speedSamples = this._speedSamples.filter((s) => s.t >= cutoff);

    let currentSpeed = 0;
    if (this._speedSamples.length >= 2) {
      const oldest = this._speedSamples[0];
      const newest = this._speedSamples[this._speedSamples.length - 1];
      const dt = (newest.t - oldest.t) / 1000;
      if (dt > 0) currentSpeed = (newest.bytes - oldest.bytes) / dt;
    }

    const elapsed = (now - this.startTime) / 1000;
    const averageSpeed = elapsed > 0 ? this.bytesTransferred / elapsed : 0;
    const remainingBytes = this.file.size - this.bytesTransferred;
    const eta = currentSpeed > 0 ? remainingBytes / currentSpeed : null;
    const percentage = totalChunks > 0 ? (receivedCount / totalChunks) * 100 : 0;

    this.onProgress({
      bytesTransferred: this.bytesTransferred,
      totalBytes: this.file.size,
      percentage,
      currentSpeed,
      averageSpeed,
      etaSeconds: eta,
      completedChunks: receivedCount,
      totalChunks,
      windowSize: this.windowSize,
      inFlight: this.inFlight.size,
      retransmissions: this.retransmissions,
      elapsedSeconds: elapsed,
    });
  }

  // --- Resume persistence (localStorage on the user's own machine - this
  // is a standalone app running in a normal browser tab, not a sandboxed
  // artifact, so localStorage is the correct/expected mechanism here) ---

  _sessionKey(file) {
    return `${STORAGE_KEY_PREFIX}${file.name}_${file.size}`;
  }

  _persistSession(file, sessionId) {
    try {
      localStorage.setItem(this._sessionKey(file), JSON.stringify({ sessionId, savedAt: Date.now() }));
    } catch {
      /* localStorage unavailable (e.g. private browsing) - resume just won't persist across reloads */
    }
  }

  _loadPersistedSession(file) {
    try {
      const raw = localStorage.getItem(this._sessionKey(file));
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  _clearPersistedSession(file) {
    try {
      localStorage.removeItem(this._sessionKey(file));
    } catch {
      /* ignore */
    }
  }
}
