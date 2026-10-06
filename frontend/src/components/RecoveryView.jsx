import { RefreshCw, WifiOff } from "lucide-react";

export default function RecoveryView({ missingChunks, totalChunks }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-400/10">
        <WifiOff className="text-amber-400" size={28} />
      </div>
      <h2 className="text-lg font-semibold text-white">Connection lost</h2>
      <p className="mt-1 text-sm text-slate-400">Reconnecting automatically...</p>

      <div className="mt-8 flex items-center gap-2 rounded-full border border-base-700 bg-base-900 px-4 py-2 text-xs text-slate-300">
        <RefreshCw size={14} className="animate-spin" />
        Session found - resuming from last acknowledged chunk
      </div>

      {typeof missingChunks === "number" && (
        <p className="mt-4 text-sm text-slate-400">
          <span className="font-semibold text-white">{missingChunks}</span> of{" "}
          <span className="font-semibold text-white">{totalChunks}</span> chunks remaining
        </p>
      )}
    </div>
  );
}
