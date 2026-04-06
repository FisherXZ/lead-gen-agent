export default function WaitingIndicator() {
  return (
    <div className="flex items-center gap-2 py-2">
      <span className="flex h-3.5 w-3.5 items-center justify-center shrink-0">
        <span className="h-2 w-2 rounded-full bg-accent-amber animate-timeline-pulse" />
      </span>
      <span className="text-[13px] text-text-tertiary">Researching...</span>
    </div>
  );
}
