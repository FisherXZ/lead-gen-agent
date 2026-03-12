/**
 * Persist research plan state in sessionStorage so it survives
 * navigation between the pipeline table and project detail page.
 */

const KEY_PREFIX = "research-plan::";
const TTL_MS = 30 * 60 * 1000; // 30 minutes

export interface PersistedResearchState {
  status: "planning" | "plan_ready" | "researching";
  plan: string;
  timestamp: number;
}

export function saveResearchState(
  projectId: string,
  state: Omit<PersistedResearchState, "timestamp">
): void {
  try {
    const entry: PersistedResearchState = { ...state, timestamp: Date.now() };
    sessionStorage.setItem(KEY_PREFIX + projectId, JSON.stringify(entry));
  } catch {
    // SSR or private browsing — no-op
  }
}

export function getResearchState(
  projectId: string
): PersistedResearchState | null {
  try {
    const raw = sessionStorage.getItem(KEY_PREFIX + projectId);
    if (!raw) return null;
    const parsed: PersistedResearchState = JSON.parse(raw);
    if (Date.now() - parsed.timestamp > TTL_MS) {
      sessionStorage.removeItem(KEY_PREFIX + projectId);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearResearchState(projectId: string): void {
  try {
    sessionStorage.removeItem(KEY_PREFIX + projectId);
  } catch {
    // no-op
  }
}

export function hasActiveResearch(projectId: string): boolean {
  return getResearchState(projectId) !== null;
}
