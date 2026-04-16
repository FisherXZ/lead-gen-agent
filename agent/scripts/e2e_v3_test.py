#!/usr/bin/env python3
"""E2E test driver for v3 research engine — compares against v2 baseline."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_client, store_discovery  # noqa: E402
from src.knowledge_base import build_knowledge_context  # noqa: E402
from src.research import run_research  # noqa: E402

# Same 2 projects from v2 e2e run (run_20260415_220344)
PROJECT_IDS = [
    ("e0d84570-8137-40c5-bfe5-20a19d00dd83", "Pepper Hammock 2100MW (BrightNight, GA) — known dev, v2=(none)(likely) FALSE POSITIVE"),
    ("c909d117-9894-440d-9da1-863115109139", "Solar Star Rhome 220MW (TX/ERCOT) — self-named SPV, v2=(none)(unknown) HONEST"),
]

# v2 baseline from prior run (run_20260415_220344)
V2_BASELINE = {
    "e0d84570-8137-40c5-bfe5-20a19d00dd83": {
        "epc": None,
        "confidence": "likely",
        "sources": 7,
        "tokens": 121539,
        "seconds": 122.2,
        "reflections": 1,
        "v1_epc": "Unknown", "v1_conf": "likely",
    },
    "c909d117-9894-440d-9da1-863115109139": {
        "epc": None,
        "confidence": "unknown",
        "sources": 1,
        "tokens": 239086,
        "seconds": 140.6,
        "reflections": 3,
        "v1_epc": "Unknown", "v1_conf": "unknown",
    },
}


def _summarize_phases(agent_log):
    phases = {}
    for entry in agent_log:
        p = entry.get("phase", "unknown")
        phases[p] = phases.get(p, 0) + 1
    return phases


async def main():
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent.parent / "tests" / "e2e_results" / f"v3_run_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"V3 e2e test run: {ts}", flush=True)
    print(f"Output: {out_dir}", flush=True)
    print(f"OPENAI_API_KEY: {'SET' if os.environ.get('OPENAI_API_KEY') else 'NOT SET — will degrade'}", flush=True)
    print(f"FIRECRAWL_API_KEY: {'SET' if os.environ.get('FIRECRAWL_API_KEY') else 'NOT SET — will degrade'}", flush=True)
    print(flush=True)

    client = get_client()
    summary = []

    for i, (pid, desc) in enumerate(PROJECT_IDS, 1):
        v2 = V2_BASELINE[pid]
        print(f"{'=' * 80}", flush=True)
        print(f"[{i}/{len(PROJECT_IDS)}] {desc}", flush=True)
        print(f"  v2: epc={v2['epc']} conf={v2['confidence']} tokens={v2['tokens']:,} time={v2['seconds']}s", flush=True)

        proj_resp = client.table("projects").select("*").eq("id", pid).limit(1).execute()
        project = proj_resp.data[0]
        kb = build_knowledge_context(project)

        print(f"  Running v3 research...", flush=True)
        start = time.time()
        try:
            result, agent_log, total_tokens = await run_research(project, knowledge_context=kb)
            elapsed = time.time() - start
            phases = _summarize_phases(agent_log)

            print(f"  ✓ Completed in {elapsed:.1f}s | tokens={total_tokens}", flush=True)
            print(f"    v3 result: {result.epc_contractor or '(none)'} ({result.confidence}) | sources={result.source_count}", flush=True)
            print(f"    Phases: {phases}", flush=True)
            # Show reflection summaries
            for entry in agent_log:
                if entry.get("phase") == "reflect":
                    print(f"      [r{entry['depth']}] {entry['summary'][:120]}", flush=True)
                    print(f"          gaps={entry.get('gaps', [])[:3]} should_continue={entry.get('should_continue')}", flush=True)

            try:
                store_discovery(pid, result, agent_log, total_tokens, project=project)
                print(f"    ✓ Stored to Supabase as pending", flush=True)
            except Exception as e:
                print(f"    ⚠ store_discovery failed: {e}", flush=True)

            # Save full trace
            with open(out_dir / f"{pid[:8]}.json", "w") as f:
                json.dump({
                    "project_id": pid,
                    "project_name": project.get("project_name"),
                    "v2_baseline": v2,
                    "v3_result": {
                        "epc_contractor": result.epc_contractor,
                        "confidence": result.confidence,
                        "agent_confidence": result.agent_confidence,
                        "source_count": result.source_count,
                        "sources": [s.model_dump() for s in result.sources],
                        "reasoning": result.reasoning if isinstance(result.reasoning, str) else result.reasoning,
                        "searches_performed": result.searches_performed,
                        "error": result.error.model_dump() if result.error else None,
                    },
                    "v3_metrics": {
                        "wall_clock_seconds": round(elapsed, 1),
                        "total_tokens": total_tokens,
                        "phases": phases,
                    },
                    "agent_log": agent_log,
                }, f, indent=2, default=str)

            summary.append({
                "project": project.get("project_name"),
                "v2_epc": v2["epc"], "v2_conf": v2["confidence"], "v2_tokens": v2["tokens"], "v2_time": v2["seconds"],
                "v3_epc": result.epc_contractor, "v3_conf": result.confidence, "v3_tokens": total_tokens, "v3_time": round(elapsed, 1),
                "v3_sources": result.source_count,
                "v3_phases": phases,
                "error": result.error.model_dump() if result.error else None,
            })
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ✗ FAILED after {elapsed:.1f}s: {e}", flush=True)
            import traceback
            traceback.print_exc()
            summary.append({"project": project.get("project_name"), "error": str(e), "seconds": round(elapsed, 1)})

        print(flush=True)

    # Comparison summary
    print("=" * 80, flush=True)
    print("V2 vs V3 COMPARISON", flush=True)
    print("=" * 80, flush=True)
    for s in summary:
        print(json.dumps(s, indent=2, default=str), flush=True)

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nFull results: {out_dir}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
