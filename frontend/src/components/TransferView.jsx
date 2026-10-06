import { Gauge, Timer, HardDrive, RefreshCw, ShieldCheck } from "lucide-react";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(2)} ${units[i]}`;
}

function formatSpeed(bytesPerSec) {
  return `${formatBytes(bytesPerSec)}/s`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined || !isFinite(seconds)) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl border border-base-700 bg-base-900 p-4">
      <div className="mb-1 flex items-center gap-1.5 text-slate-500">
        <Icon size={14} />
        <span className="text-[11px] font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-lg font-semibold text-white tabular-nums">{value}</p>
    </div>
  );
}

export default function TransferView({ fileName, progress }) {
  const p = progress || {};
  const pct = Math.min(100, p.percentage || 0);

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Transferring</p>
      <h2 className="mb-6 truncate text-lg font-semibold text-white">{fileName}</h2>

      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-3xl font-bold text-white tabular-nums">{pct.toFixed(1)}%</span>
        <span className="text-sm text-slate-400 tabular-nums">
          {formatBytes(p.bytesTransferred)} / {formatBytes(p.totalBytes)}
        </span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-base-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent-500 to-accent-400 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard icon={Gauge} label="Current Speed" value={formatSpeed(p.currentSpeed)} />
        <StatCard icon={Gauge} label="Average Speed" value={formatSpeed(p.averageSpeed)} />
        <StatCard icon={Timer} label="ETA" value={formatEta(p.etaSeconds)} />
        <StatCard icon={HardDrive} label="Chunks" value={`${p.completedChunks ?? 0} / ${p.totalChunks ?? 0}`} />
        <StatCard icon={RefreshCw} label="Retransmissions" value={p.retransmissions ?? 0} />
        <StatCard icon={ShieldCheck} label="Window / In-Flight" value={`${p.windowSize ?? 0} / ${p.inFlight ?? 0}`} />
      </div>
    </div>
  );
}
