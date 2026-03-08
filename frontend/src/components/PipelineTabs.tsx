"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

const TABS = [
  { key: "projects", label: "Projects", href: "/" },
  { key: "epc", label: "EPC Research", href: "/?tab=epc" },
];

export default function PipelineTabs() {
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") || "projects";

  return (
    <div className="mb-6 flex gap-1 border-b border-slate-200">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.key;
        return (
          <Link
            key={tab.key}
            href={tab.href}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
              isActive
                ? "text-slate-900"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab.label}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-slate-900" />
            )}
          </Link>
        );
      })}
    </div>
  );
}
