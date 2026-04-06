"use client";

const PROMPTS = [
  "What's new in ERCOT this week?",
  "What do we know about Blattner Energy?",
  "Find contacts at Signal Energy",
  "Any projects over 300MW entering construction?",
  "Show me all pending reviews",
  "Which EPCs are most active in CAISO?",
];

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void;
}

export default function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {PROMPTS.map((prompt) => (
        <button
          key={prompt}
          onClick={() => onSelect(prompt)}
          className="rounded-full border border-border-default bg-surface-raised px-4 py-2 text-sm text-text-secondary transition-colors hover:border-border-focus hover:bg-surface-overlay hover:text-text-primary"
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}
