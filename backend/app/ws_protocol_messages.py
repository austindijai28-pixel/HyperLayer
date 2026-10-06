"""
JSON control-message schema exchanged over the WebSocket alongside the
binary chunk frames (see protocol.py for the binary format).

Text frames = control/telemetry JSON.
Binary frames = 56-byte header + chunk payload.

Client -> Server
  INIT            {type, file_name, file_size, chunk_size, file_hash?}
  RESUME_REQUEST  {type, session_id}

Server -> Client
  SESSION_READY   {type, session_id, file_id, total_chunks, chunk_size,
                    window_size, missing_chunks, resumed}
  CHUNK_ACK       {type, chunk_index, window_size, in_flight, received_count, total_chunks}
  CHUNK_RETRY     {type, chunk_index, reason, retry_count}
  TRANSFER_COMPLETE {type, integrity_verified, file_hash, duration_seconds}
  ERROR           {type, code, message}
"""

MSG_INIT = "INIT"
MSG_RESUME_REQUEST = "RESUME_REQUEST"
MSG_SESSION_READY = "SESSION_READY"
MSG_CHUNK_ACK = "CHUNK_ACK"
MSG_CHUNK_RETRY = "CHUNK_RETRY"
MSG_TRANSFER_COMPLETE = "TRANSFER_COMPLETE"
MSG_ERROR = "ERROR"

ERR_INVALID_SESSION = "INVALID_SESSION"
ERR_INVALID_CHUNK = "INVALID_CHUNK"
ERR_MALFORMED_FRAME = "MALFORMED_FRAME"
ERR_HASH_MISMATCH = "HASH_MISMATCH"
ERR_DISK_WRITE_FAILED = "DISK_WRITE_FAILED"
ERR_INSUFFICIENT_STORAGE = "INSUFFICIENT_STORAGE"
ERR_RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
ERR_DUPLICATE_CHUNK = "DUPLICATE_CHUNK"  # informational, not fatal
ERR_INTERNAL = "INTERNAL_ERROR"
