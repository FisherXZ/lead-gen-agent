"use client";

interface ConfidenceBadgeProps {
  confidence: string;
  sourceCount?: number;
  warning?: string;
  size?: "sm" | "md";
}

const BADGE_STYLES: Record<string, string> = {
  confirmed: "bg-emerald-100 text-emerald-700",
  likely: "bg-orange-100 text-orange-700",
  possible: "bg-amber-100 text-amber-700",
  unknown: "bg-slate-100 text-slate-600",
};

export default function ConfidenceBadge({
  confidence,
  sourceCount,
  warning,
  size = "md",
}: ConfidenceBadgeProps) {
  const style = BADGE_STYLES[confidence] || BADGE_STYLES.unknown;

  const label =
    sourceCount && sourceCount > 0
      ? `${confidence} (${sourceCount} source${sourceCount !== 1 ? "s" : ""})`
      : confidence;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-block rounded-full font-semibold capitalize ${style} ${size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-0.5 text-xs"}`}
      >
        {label}
      </span>
      {warning && (
        <span className="inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-600">
          Unverified
        </span>
      )}
    </span>
  );
}
