"use client";

interface FileAttachmentProps {
  file: {
    name: string;
    type: string;
    preview?: string; // data URL for image preview
    size: number;
  };
  onRemove?: () => void;
  compact?: boolean; // compact mode for message history (no remove button)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(type: string) {
  if (type === "application/pdf") {
    return (
      <div className="flex h-full w-full items-center justify-center rounded bg-red-100 text-[9px] font-bold text-red-600">
        PDF
      </div>
    );
  }
  if (type.startsWith("text/") || type === "text/csv") {
    return (
      <div className="flex h-full w-full items-center justify-center rounded bg-blue-100 text-[9px] font-bold text-blue-600">
        TXT
      </div>
    );
  }
  return (
    <div className="flex h-full w-full items-center justify-center rounded bg-slate-100 text-[9px] font-bold text-slate-500">
      FILE
    </div>
  );
}

export default function FileAttachment({
  file,
  onRemove,
  compact = false,
}: FileAttachmentProps) {
  const isImage = file.type.startsWith("image/");

  if (compact) {
    // Compact display for message history
    if (isImage && file.preview) {
      return (
        <img
          src={file.preview}
          alt={file.name}
          className="max-h-48 max-w-xs rounded-lg border border-white/20"
        />
      );
    }
    return (
      <div className="inline-flex items-center gap-1.5 rounded-md bg-white/10 px-2 py-1">
        <div className="h-5 w-5 shrink-0">{getFileIcon(file.type)}</div>
        <span className="text-xs opacity-80">{file.name}</span>
      </div>
    );
  }

  // Input area attachment chip
  return (
    <div className="group relative flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 shadow-sm">
      {/* Thumbnail or icon */}
      <div className="h-8 w-8 shrink-0 overflow-hidden rounded">
        {isImage && file.preview ? (
          <img
            src={file.preview}
            alt={file.name}
            className="h-full w-full object-cover"
          />
        ) : (
          getFileIcon(file.type)
        )}
      </div>

      {/* Info */}
      <div className="min-w-0">
        <p className="max-w-[160px] truncate text-xs font-medium text-slate-700">
          {file.name}
        </p>
        <p className="text-[10px] text-slate-400">{formatSize(file.size)}</p>
      </div>

      {/* Remove button */}
      {onRemove && (
        <button
          onClick={onRemove}
          className="ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 transition-colors hover:bg-red-100 hover:text-red-500"
          title="Remove"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}
    </div>
  );
}
