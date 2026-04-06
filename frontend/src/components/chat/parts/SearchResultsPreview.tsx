"use client";

interface SearchResult {
  title?: string;
  url?: string;
  snippet?: string;
}

interface SearchResultsPreviewProps {
  data: Record<string, unknown>;
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function SearchResultsPreview({ data }: SearchResultsPreviewProps) {
  const results = (Array.isArray(data.results) ? data.results : []) as SearchResult[];
  if (results.length === 0) {
    return (
      <p className="px-3 py-2 text-[12px] text-text-tertiary">No results found</p>
    );
  }

  const visible = results.slice(0, 3);
  const remaining = results.length - visible.length;

  return (
    <div className="flex flex-col gap-1 px-3 py-2">
      {visible.map((r, i) => (
        <a
          key={i}
          href={r.url}
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-baseline gap-0 text-[12px] leading-snug hover:underline truncate"
        >
          <span className="font-medium text-text-secondary group-hover:text-text-primary shrink-0">
            {r.url ? extractDomain(r.url) : "source"}
          </span>
          {r.title && (
            <>
              <span className="text-text-tertiary mx-1.5 shrink-0">&mdash;</span>
              <span className="text-text-tertiary group-hover:text-text-secondary truncate">
                {r.title}
              </span>
            </>
          )}
        </a>
      ))}
      {remaining > 0 && (
        <span className="text-[11px] text-text-tertiary">
          and {remaining} more
        </span>
      )}
    </div>
  );
}
