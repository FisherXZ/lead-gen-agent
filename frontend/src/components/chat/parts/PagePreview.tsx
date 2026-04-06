"use client";

interface PagePreviewProps {
  data: Record<string, unknown>;
  input?: Record<string, unknown>;
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function extractFirstSentence(text: string): string {
  // Get first meaningful sentence from page content
  const lines = text.split("\n").filter((l) => l.trim().length > 20);
  if (lines.length === 0) return "";
  const first = lines[0].trim();
  // Truncate at first sentence boundary or 120 chars
  const sentenceEnd = first.search(/[.!?]\s/);
  if (sentenceEnd > 0 && sentenceEnd < 120) {
    return first.slice(0, sentenceEnd + 1);
  }
  return first.length > 120 ? first.slice(0, 120) + "..." : first;
}

export default function PagePreview({ data, input }: PagePreviewProps) {
  const rawUrl = input?.url as string | undefined;
  const url = rawUrl && /^https?:\/\//i.test(rawUrl) ? rawUrl : undefined;
  const title = data.title as string | undefined;
  const text = data.text as string | undefined;
  const extract = text ? extractFirstSentence(text) : null;

  if (!title && !extract) return null;

  return (
    <div className="flex flex-col gap-0.5 px-3 py-2">
      {title && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[13px] font-medium text-text-secondary hover:text-text-primary hover:underline truncate"
        >
          {title}
          {url && (
            <span className="ml-1.5 text-[11px] text-text-tertiary font-normal">
              {extractDomain(url)}
            </span>
          )}
        </a>
      )}
      {extract && (
        <p className="text-[12px] text-text-tertiary truncate">{extract}</p>
      )}
    </div>
  );
}
