import { useCallback, useEffect, useRef, useState } from "react";
import type { UIMessage } from "ai";

const DEFAULT_TIMEOUT_MS = 30_000;

export function useFrozenDetector(
  isLoading: boolean,
  messages: UIMessage[],
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): { isFrozen: boolean; reset: () => void } {
  // State
  const [isFrozen, setIsFrozen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fingerprintRef = useRef<string>("");

  // Compute a cheap fingerprint from messages
  // Changes whenever new text/tool parts stream in
  const lastMsg = messages.at(-1);
  const lastPart = lastMsg?.parts?.at(-1);
  const contentLen = lastPart && "text" in lastPart ? (lastPart as { text: string }).text.length : 0;
  const fingerprint = isLoading
    ? `${messages.length}:${lastMsg?.parts?.length ?? 0}:${contentLen}`
    : "";

  useEffect(() => {
    // Only run while loading
    if (!isLoading) {
      // Clear timer and frozen state when loading stops
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      setIsFrozen(false);
      fingerprintRef.current = "";
    } else if (fingerprint !== fingerprintRef.current) {
      // If fingerprint changed, content is flowing — reset timer
      fingerprintRef.current = fingerprint;
      setIsFrozen(false);

      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        console.warn("Frozen response detected", {
          fingerprint,
          timestamp: new Date().toISOString(),
        });
        setIsFrozen(true);
      }, timeoutMs);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isLoading, fingerprint, timeoutMs]);

  const reset = useCallback(() => {
    setIsFrozen(false);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  return { isFrozen, reset };
}
