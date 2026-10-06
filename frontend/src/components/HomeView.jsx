import { useRef, useState, useEffect } from "react";
import {
  UploadCloud, FileIcon, Zap, Laptop, Edit2, Check, Share2,
  Info, Download, FolderOpen, ArrowDownToLine, ArrowUpFromLine,
  RefreshCw, CheckCircle2,
} from "lucide-react";

const CHUNK_OPTIONS = [
  { label: "1 MB", value: 1 * 1024 * 1024 },
  { label: "5 MB", value: 5 * 1024 * 1024 },
  { label: "10 MB", value: 10 * 1024 * 1024 },
  { label: "25 MB", value: 25 * 1024 * 1024 },
];

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(2)} ${units[i]}`;
}

function formatDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

// ─── Receive Mode ──────────────────────────────────────────────────────────
function ReceiveMode({ hostInfo }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);

  const hostIp = hostInfo?.local_ip || "127.0.0.1";
  const hostPort = hostInfo?.port || 8000;
  const hostUrl = `http://${hostIp}:${hostPort}`;

  const fetchFiles = () => {
    setLoading(true);
    fetch("/api/downloads")
      .then((r) => r.json())
      .then((data) => setFiles(data.files || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchFiles();
    const id = setInterval(fetchFiles, 4000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      {/* Waiting banner */}
      <div className="mb-6 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
            <ArrowDownToLine size={18} />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Receive Mode — Active</p>
            <p className="text-sm font-semibold text-white">Waiting for incoming files…</p>
          </div>
        </div>
        <div className="border-t border-emerald-500/20 pt-3 text-xs text-slate-300 flex items-start gap-2">
          <Info size={14} className="text-emerald-400 shrink-0 mt-0.5" />
          <span>
            Files sent to <strong className="text-emerald-300 font-mono select-all">{hostUrl}</strong> will
            appear below automatically. Share this URL with the sender.
          </span>
        </div>
      </div>

      {/* Sender instructions card */}
      <div className="mb-6 rounded-xl border border-base-800 bg-base-900/60 p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-200 mb-1.5">
          <Share2 size={15} className="text-emerald-400" />
          <span>How the sender connects:</span>
        </div>
        <ol className="list-decimal list-inside text-xs text-slate-400 space-y-1 ml-1">
          <li>Connect to the <strong>same Wi-Fi network</strong> as this device.</li>
          <li>Open a browser and go to: <strong className="text-emerald-300 font-mono select-all">{hostUrl}</strong></li>
          <li>Select <strong>Send Mode</strong>, pick a file, and click <strong>Start Transfer</strong>.</li>
        </ol>
      </div>

      {/* Received files list */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Received files {files.length > 0 && `(${files.length})`}
        </p>
        <button
          onClick={fetchFiles}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-accent-400"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {files.length === 0 ? (
        <div className="rounded-2xl border-2 border-dashed border-base-700 bg-base-900 p-10 text-center">
          <FolderOpen className="mx-auto mb-3 text-slate-600" size={36} />
          <p className="text-sm text-slate-400">No files received yet</p>
          <p className="mt-1 text-xs text-slate-600">Files will appear here as they arrive</p>
        </div>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <div
              key={f.name}
              className="flex items-center gap-3 rounded-xl border border-base-700 bg-base-900 p-3.5"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-base-800">
                <FileIcon size={18} className="text-accent-400" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-200">{f.name}</p>
                <p className="text-xs text-slate-500">
                  {formatBytes(f.size)} · {formatDate(f.modified_at)}
                </p>
              </div>
              <a
                href={`/api/downloads/${encodeURIComponent(f.name)}`}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-base-700 text-slate-400 hover:border-accent-500 hover:text-accent-400"
                title="Download"
              >
                <Download size={15} />
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Send Mode ─────────────────────────────────────────────────────────────
function SendMode({ connectionStatus, onStart, hostInfo, onHostInfoUpdate }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [chunkSize, setChunkSize] = useState(CHUNK_OPTIONS[1].value);
  const [dragOver, setDragOver] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [tempDeviceName, setTempDeviceName] = useState("");

  const handleFiles = (files) => {
    if (files && files[0]) setFile(files[0]);
  };

  const handleSaveName = async () => {
    if (!tempDeviceName.trim()) return;
    try {
      await fetch("/api/device_name", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_name: tempDeviceName.trim() }),
      });
      setIsEditingName(false);
      if (onHostInfoUpdate) onHostInfoUpdate();
    } catch {
      // ignore
    }
  };

  const hostIp = hostInfo?.local_ip || "127.0.0.1";
  const hostPort = hostInfo?.port || 8000;
  const hostUrl = `http://${hostIp}:${hostPort}`;
  const deviceName = hostInfo?.device_name || "Host Receiver PC";

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      {/* Receiver Device / Username Card */}
      <div className="mb-6 rounded-2xl border border-accent-500/30 bg-accent-500/10 p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-500/20 text-accent-400">
              <Laptop size={18} />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Receiving Device / Host</p>
              {isEditingName ? (
                <div className="mt-1 flex items-center gap-2">
                  <input
                    type="text"
                    value={tempDeviceName}
                    onChange={(e) => setTempDeviceName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSaveName()}
                    placeholder="Enter Receiver Name (e.g. Ashin)"
                    className="rounded-lg border border-base-700 bg-base-950 px-2.5 py-1 text-xs text-white focus:border-accent-400 focus:outline-none"
                    autoFocus
                  />
                  <button
                    onClick={handleSaveName}
                    className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500 text-white hover:bg-accent-400"
                  >
                    <Check size={14} />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{deviceName}</span>
                  <button
                    onClick={() => { setTempDeviceName(deviceName); setIsEditingName(true); }}
                    className="text-slate-400 hover:text-accent-400"
                    title="Change Receiver Display Name"
                  >
                    <Edit2 size={13} />
                  </button>
                </div>
              )}
            </div>
          </div>
          <span className="rounded-md bg-base-900 border border-base-700 px-2.5 py-1 text-[11px] font-mono text-slate-300">
            {hostUrl}
          </span>
        </div>
        <div className="mt-3 border-t border-accent-500/20 pt-2.5 text-xs text-slate-300 flex items-center gap-2">
          <CheckCircle2 size={14} className="text-accent-400 shrink-0" />
          <span>
            Your file will be sent to <strong>{deviceName}</strong> ({hostIp}) on this network.
          </span>
        </div>
      </div>

      {/* Drag & Drop */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
          dragOver ? "border-accent-400 bg-accent-500/5" : "border-base-700 bg-base-900 hover:border-base-600"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <UploadCloud className="mx-auto mb-3 text-slate-500" size={36} />
        <p className="text-sm text-slate-300">Drag &amp; drop a file here, or click to browse</p>
        <p className="mt-1 text-xs text-slate-500">Streamed in chunks over local Wi-Fi to {deviceName}</p>
      </div>

      {file && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-base-700 bg-base-900 p-4">
          <FileIcon size={20} className="text-accent-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-200">{file.name}</p>
            <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
          </div>
        </div>
      )}

      <div className="mt-6">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Chunk size</p>
        <div className="flex gap-2 flex-wrap">
          {CHUNK_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setChunkSize(opt.value)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                chunkSize === opt.value
                  ? "border-accent-400 bg-accent-500/15 text-accent-400"
                  : "border-base-700 text-slate-400 hover:border-base-600"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <button
        disabled={!file || connectionStatus !== "CONNECTED"}
        onClick={() => onStart(file, chunkSize)}
        className="mt-8 w-full rounded-xl bg-gradient-to-r from-accent-500 to-accent-400 py-3 text-sm font-semibold text-white shadow-lg shadow-accent-500/20 transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
      >
        Start Transfer
      </button>
      {connectionStatus !== "CONNECTED" && (
        <p className="mt-2 text-center text-xs text-slate-500">Waiting for server connection…</p>
      )}
    </div>
  );
}

// ─── HomeView (mode selector + sub-views) ───────────────────────────────────
export default function HomeView({ connectionStatus, onStart, hostInfo, onHostInfoUpdate }) {
  const [mode, setMode] = useState(null); // null = not chosen yet

  if (mode === null) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 flex flex-col items-center">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-accent-400 to-accent-500 shadow-lg shadow-accent-500/20">
            <Zap size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-white">HyperLocal</h1>
            <p className="text-xs text-slate-400">High-speed resumable transfer over local Wi-Fi</p>
          </div>
        </div>

        <p className="mt-8 mb-6 text-sm text-slate-400">What would you like to do?</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-sm">
          {/* Send */}
          <button
            onClick={() => setMode("send")}
            className="flex flex-col items-center gap-3 rounded-2xl border-2 border-accent-500/40 bg-accent-500/10 p-6 text-center hover:border-accent-400 hover:bg-accent-500/20 transition-colors"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-500/20 text-accent-400">
              <ArrowUpFromLine size={22} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Send a File</p>
              <p className="mt-0.5 text-xs text-slate-400">Pick a file and transfer it over Wi-Fi</p>
            </div>
          </button>

          {/* Receive */}
          <button
            onClick={() => setMode("receive")}
            className="flex flex-col items-center gap-3 rounded-2xl border-2 border-emerald-500/40 bg-emerald-500/10 p-6 text-center hover:border-emerald-400 hover:bg-emerald-500/20 transition-colors"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-400">
              <ArrowDownToLine size={22} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Receive a File</p>
              <p className="mt-0.5 text-xs text-slate-400">Wait for a file sent to this device</p>
            </div>
          </button>
        </div>

        <p className="mt-8 text-xs text-slate-600">Both devices must be on the same Wi-Fi network</p>
      </div>
    );
  }

  return (
    <>
      {/* Mode switcher strip */}
      <div className="border-b border-base-800 bg-base-950/60">
        <div className="mx-auto max-w-2xl px-4 py-2 flex items-center gap-2">
          <button
            onClick={() => setMode("send")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "send"
                ? "bg-accent-500/20 text-accent-400 border border-accent-500/40"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <ArrowUpFromLine size={13} /> Send
          </button>
          <button
            onClick={() => setMode("receive")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "receive"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <ArrowDownToLine size={13} /> Receive
          </button>
          <button
            onClick={() => setMode(null)}
            className="ml-auto text-xs text-slate-600 hover:text-slate-400"
          >
            ← Back
          </button>
        </div>
      </div>

      {mode === "send" && (
        <SendMode
          connectionStatus={connectionStatus}
          onStart={onStart}
          hostInfo={hostInfo}
          onHostInfoUpdate={onHostInfoUpdate}
        />
      )}
      {mode === "receive" && <ReceiveMode hostInfo={hostInfo} />}
    </>
  );
}
