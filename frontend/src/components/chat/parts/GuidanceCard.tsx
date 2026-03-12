"use client";

interface GuidanceCardProps {
  data: {
    status_summary?: string;
    question?: string;
    options?: string[];
    awaiting_response?: boolean;
    error?: string;
  };
}

export default function GuidanceCard({ data }: GuidanceCardProps) {
  if (data.error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Guidance error: {data.error}
      </div>
    );
  }

  function handleOptionClick(option: string) {
    // Dispatch a custom event that ChatInterface listens for
    // to populate the chat input without auto-sending
    window.dispatchEvent(
      new CustomEvent("populate-chat-input", { detail: { text: option } })
    );
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      {data.status_summary && (
        <p className="mb-2 text-sm text-slate-600">{data.status_summary}</p>
      )}

      {data.question && (
        <p className="mb-3 text-sm font-medium text-slate-900">
          {data.question}
        </p>
      )}

      {data.options && data.options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.options.map((option, i) => (
            <button
              key={i}
              onClick={() => handleOptionClick(option)}
              className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-100"
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
