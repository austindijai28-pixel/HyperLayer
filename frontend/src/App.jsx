import { useEffect, useRef, useState } from "react";
import { TransferEngine, ConnectionStatus, TransferPhase } from "./lib/transferEngine.js";
import StatusBadge from "./components/StatusBadge.jsx";
import HomeView from "./components/HomeView.jsx";
import TransferView from "./components/TransferView.jsx";
import RecoveryView from "./components/RecoveryView.jsx";
import CompleteView from "./components/CompleteView.jsx";

export default function App() {
  const engineRef = useRef(null);
  const [connectionStatus, setConnectionStatus] = useState(ConnectionStatus.CONNECTING);
  const [phase, setPhase] = useState(TransferPhase.IDLE);
  const [progress, setProgress] = useState(null);
  const [completeResult, setCompleteResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [currentFile, setCurrentFile] = useState(null);
  const [hostInfo, setHostInfo] = useState(null);

  const fetchHostInfo = () => {
    fetch("/api/info")
      .then((res) => res.json())
      .then((data) => setHostInfo(data))
      .catch(() => {});
  };

  useEffect(() => {
    fetchHostInfo();
    const engine = new TransferEngine({
      onConnectionStatus: setConnectionStatus,
      onPhase: setPhase,
      onProgress: setProgress,
      onError: (code, message) => setErrorMsg(`${code}: ${message}`),
      onComplete: (result) => setCompleteResult(result),
    });
    engineRef.current = engine;
    engine.connect();
    return () => engine.disconnect();
  }, []);

  const handleStart = async (file, chunkSize) => {
    setCurrentFile(file);
    setErrorMsg(null);
    await engineRef.current.startTransfer(file, chunkSize);
  };

  const handleReset = () => {
    setPhase(TransferPhase.IDLE);
    setCompleteResult(null);
    setProgress(null);
    setCurrentFile(null);
  };

  return (
    <div className="min-h-screen bg-base-950">
      <header className="sticky top-0 z-10 border-b border-base-800 bg-base-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <span className="text-sm font-medium text-slate-300">HyperLocal</span>
          <StatusBadge status={connectionStatus} />
        </div>
      </header>

      {errorMsg && (
        <div className="mx-auto mt-4 max-w-2xl px-4">
          <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-2 text-xs text-red-300">
            {errorMsg}
          </div>
        </div>
      )}

      {phase === TransferPhase.IDLE && (
        <HomeView
          connectionStatus={connectionStatus}
          onStart={handleStart}
          hostInfo={hostInfo}
          onHostInfoUpdate={fetchHostInfo}
        />
      )}
      {phase === TransferPhase.TRANSFERRING && (
        <TransferView fileName={currentFile?.name} progress={progress} />
      )}
      {phase === TransferPhase.RECOVERY && (
        <RecoveryView
          missingChunks={progress ? progress.totalChunks - progress.completedChunks : undefined}
          totalChunks={progress?.totalChunks}
        />
      )}
      {(phase === TransferPhase.COMPLETE) && (
        <CompleteView result={completeResult} onReset={handleReset} />
      )}
      {phase === TransferPhase.ERROR && (
        <div className="mx-auto max-w-2xl px-4 py-16 text-center">
          <p className="text-sm text-red-400">{errorMsg || "Transfer failed."}</p>
          <button
            onClick={handleReset}
            className="mt-6 rounded-xl border border-base-700 px-5 py-2.5 text-sm font-medium text-slate-300 hover:border-base-600"
          >
            Start over
          </button>
        </div>
      )}
    </div>
  );
}
