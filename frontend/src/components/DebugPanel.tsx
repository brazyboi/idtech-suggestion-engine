import { useState } from "react";

interface DebugPanelProps {
  collectedInfo: Record<string, unknown>;
  nextState: string | undefined;
  messageCount: number;
}

export default function DebugPanel({
  collectedInfo,
  nextState,
  messageCount,
}: DebugPanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 z-50 rounded-full bg-gray-800 px-3 py-1 text-xs text-green-400 opacity-60 hover:opacity-100 font-mono"
      >
        Debug
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 max-h-[60vh] overflow-y-auto rounded-lg border border-gray-600 bg-gray-900 p-3 font-mono text-xs shadow-2xl">
      <div className="flex items-center justify-between mb-2">
        <span className="text-green-400 font-bold text-sm">Debug Panel</span>
        <button
          onClick={() => setIsOpen(false)}
          className="text-gray-400 hover:text-white"
        >
          ✕
        </button>
      </div>

      {/* State */}
      <div className="mb-2">
        <span className="text-gray-400">nextState: </span>
        <span className={`${nextState ? "text-yellow-300" : "text-gray-500"}`}>
          {nextState ?? "N/A"}
        </span>
      </div>

      {/* Message count */}
      <div className="mb-2">
        <span className="text-gray-400">messages: </span>
        <span className="text-cyan-300">{messageCount}</span>
      </div>

      {/* Collected Info */}
      <div>
        <span className="text-gray-400">collectedInfo:</span>
        <pre className="mt-1 whitespace-pre-wrap break-all text-gray-300 border-t border-gray-700 pt-1">
          {JSON.stringify(collectedInfo, null, 2) || "{ }"}
        </pre>
      </div>
    </div>
  );
}
