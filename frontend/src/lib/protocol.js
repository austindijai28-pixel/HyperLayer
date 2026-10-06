// Mirrors backend/app/protocol.py exactly.
//
// Binary frame layout (56-byte header, big-endian):
//   FILE_ID (16 bytes)  | CHUNK_INDEX (4 bytes, uint32) |
//   PAYLOAD_LENGTH (4 bytes, uint32) | SHA-256 (32 bytes) | PAYLOAD

export const HEADER_SIZE = 56;

// file_id must be a 16-byte Uint8Array (see uuidToBytes below).
export function packChunkFrame(fileIdBytes, chunkIndex, payload, sha256Bytes) {
  const header = new ArrayBuffer(HEADER_SIZE);
  const view = new DataView(header);
  const headerBytes = new Uint8Array(header);

  headerBytes.set(fileIdBytes, 0); // 16 bytes
  view.setUint32(16, chunkIndex, false); // big-endian
  view.setUint32(20, payload.byteLength, false);
  headerBytes.set(sha256Bytes, 24); // 32 bytes

  const frame = new Uint8Array(HEADER_SIZE + payload.byteLength);
  frame.set(headerBytes, 0);
  frame.set(new Uint8Array(payload), HEADER_SIZE);
  return frame.buffer;
}

// Parses a UUID string ("xxxxxxxx-xxxx-...") into 16 raw bytes.
export function uuidToBytes(uuidStr) {
  const hex = uuidStr.replace(/-/g, "");
  const bytes = new Uint8Array(16);
  for (let i = 0; i < 16; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

export function bytesToHex(bytes) {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
