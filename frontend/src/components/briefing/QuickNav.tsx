// frontend/src/components/briefing/QuickNav.tsx
"use client";

import Link from "next/link";

const NAV_LINKS = [
  { label: "Pipeline", href: "/projects" },
  { label: "Review Queue", href: "/review" },
  { label: "Actions", href: "/actions" },
  { label: "Map", href: "/map" },
  { label: "Solarina", href: "/agent" },
] as const;

export default function QuickNav() {
  return (
    <div className="flex flex-wrap gap-2">
      {NAV_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-md border border-border-subtle px-3 py-1 text-xs text-text-tertiary transition-colors hover:border-border-default hover:text-text-secondary"
        >
          {link.label} →
        </Link>
      ))}
    </div>
  );
}
