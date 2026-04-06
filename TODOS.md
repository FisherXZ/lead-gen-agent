# TODOS

## Agent Self-Management (2026-03-29)

### Baseline measurement
- **What:** Run 20 projects through the current system (before todo/think tools) and record: iterations used, confidence level, human reviewer agreement, wasted iteration count.
- **Why:** Without before-metrics, can't prove the todo system improved anything. The outside voice flagged this during CEO review.
- **Effort:** S (human: ~30min / CC: ~15min for analysis)
- **Priority:** P2
- **Depends on:** Nothing. Can run anytime before or after shipping the feature.

### Validate bottleneck hypothesis
- **What:** Sample 10 "unknown" research outcomes. Read agent_logs. Categorize failures: (a) agent forgot to check something (planning failure), (b) agent repeated same searches (goal drift), (c) information doesn't exist publicly (inherent limitation).
- **Why:** If >50% of unknowns are information-availability problems, the todo system won't help those cases. Knowing the split tells you where to invest next.
- **Effort:** S (human: ~30min manual log reading)
- **Priority:** P2
- **Depends on:** Having existing research runs with agent_logs in the DB.

### Plan templates per project type
- **What:** After observing organic todo plans across ~50 research runs, create 2-3 starter templates: (A) known developer, publicly traded (start with SEC EDGAR), (B) known developer, private (start with web search + KB), (C) minimal info (start broad).
- **Why:** Reduces the agent's "cold start" problem where the first 2-3 turns are spent figuring out what to do.
- **Effort:** S (human: ~2hr / CC: ~15min)
- **Priority:** P3
- **Depends on:** Agent self-management shipped and producing organic plan data.
