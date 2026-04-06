"use client";

interface ThinkCardProps {
  data: {
    recorded?: boolean;
    thought?: string;
  };
  input?: {
    thought?: string;
  };
}

export default function ThinkCard({ data, input }: ThinkCardProps) {
  // The thought text is in the input (what the agent sent), not the output
  // (which just returns {recorded: true} to save tokens)
  const thought = input?.thought;

  if (!thought) return null;

  return (
    <div className="px-3 py-2">
      <p className="text-sm italic text-text-tertiary leading-relaxed">
        {thought}
      </p>
    </div>
  );
}
