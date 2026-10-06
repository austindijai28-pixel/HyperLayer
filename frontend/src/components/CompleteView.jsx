import { CheckCircle2, XCircle, RotateCcw } from "lucide-react";

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(2)} ${units[i]}`;
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function CompleteView({ result, onReset }) {
  if (!result) return null;
  const { fileName, fileSize, durationSeconds, integrityVerified, retransmissions } = result;
  const avgSpeed = durationSeconds > 0 ? fileSize / durationSeconds : 0;

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <div className={`mb-4 flex h-16 w-16 items-center justify-center rounded-full ${integrityVerified ? "bg-emerald-400/10" : "bg-red-400/10"}`}>
        {integrityVerified ? (
          <CheckCircle2 className="text-emerald-400" size={32} />
        ) : (
          <XCircle className="text-red-400" size={32} />
        )}
      </div>
      <h2 className="text-xl font-semibold text-white">
        {integrityVerified ? "Transfer Complete" : "Transfer Finished - Integrity Check Failed"}
      </h2>
      <p className="mt-1 truncate text-sm text-slate-400">{fileName}</p>

      <div className="mt-8 grid w-full grid-cols-2 gap-3 text-left">
        <div className="rounded-xl border border-base-700 bg-base-900 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Size</p>
          <p className="text-sm font-semibold text-white">{formatBytes(fileSize)}</p>
        </div>
        <div className="rounded-xl border border-base-700 bg-base-900 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Duration</p>
          <p className="text-sm font-semibold text-white">{formatDuration(durationSeconds)}</p>
        </div>
        <div className="rounded-xl border border-base-700 bg-base-900 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Average Speed</p>
          <p className="text-sm font-semibold text-white">{formatBytes(avgSpeed)}/s</p>
        </div>
        <div className="rounded-xl border border-base-700 bg-base-900 p-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Retransmissions</p>
          <p className="text-sm font-semibold text-white">{retransmissions}</p>
        </div>
      </div>

      <p className={`mt-4 text-xs font-medium ${integrityVerified ? "text-emerald-400" : "text-red-400"}`}>
        Integrity: {integrityVerified ? "VERIFIED (SHA-256 match)" : "MISMATCH"}
      </p>

      <button
        onClick={onReset}
        className="mt-8 inline-flex items-center gap-2 rounded-xl border border-base-700 px-5 py-2.5 text-sm font-medium text-slate-300 hover:border-base-600"
      >
        <RotateCcw size={16} />
        Send another file
      </button>
    </div>
  );
}
