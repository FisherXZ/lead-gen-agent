"use client";

interface CitationBadgeProps {
  href: string;
  children: React.ReactNode;
  index: number;
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function CitationBadge({ href, children, index }: CitationBadgeProps) {
  const domain = extractDomain(href);
  const title = typeof children === "string" ? children : String(children);

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      role="link"
      aria-label={`Source ${index}: ${domain} - ${title}`}
      className="inline-flex items-center gap-1 rounded bg-accent-amber/15 px-1.5 py-0.5 text-[12px] text-text-secondary no-underline hover:bg-accent-amber/25 transition-colors align-baseline"
      title={`${title}\n${href}`}
    >
      <span className="text-text-tertiary font-medium">{index}</span>
      <span>{domain}</span>
    </a>
  );
}
