import { Wifi, WifiOff, Loader2 } from "lucide-react";
import { ConnectionStatus } from "../lib/transferEngine.js";

export default function StatusBadge({ status }) {
  const map = {
    [ConnectionStatus.CONNECTED]: { icon: Wifi, text: "Connected", cls: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10" },
    [ConnectionStatus.CONNECTING]: { icon: Loader2, text: "Connecting", cls: "text-amber-400 border-amber-400/30 bg-amber-400/10", spin: true },
    [ConnectionStatus.RECONNECTING]: { icon: Loader2, text: "Reconnecting", cls: "text-amber-400 border-amber-400/30 bg-amber-400/10", spin: true },
    [ConnectionStatus.DISCONNECTED]: { icon: WifiOff, text: "Disconnected", cls: "text-red-400 border-red-400/30 bg-red-400/10" },
  };
  const { icon: Icon, text, cls, spin } = map[status] || map[ConnectionStatus.DISCONNECTED];
  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${cls}`}>
      <Icon size={14} className={spin ? "animate-spin" : ""} />
      {text}
    </div>
  );
}
