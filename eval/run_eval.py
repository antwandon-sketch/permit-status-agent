"""
Eval harness entrypoint: measures real reliability of check_permit_status
and get_inspection_history against the live EnerGov portal.

Usage (from repo root): ./venv/bin/python3 -m eval.run_eval

Writes, all under eval/:
  sample_<ts>.json   — exactly how the sample was built: every seed query
                        run, how many results each returned, how many
                        were kept, the full deduped candidate pool, and
                        the randomly-selected subset actually tested.
  raw_<ts>.jsonl      — one line per (item, tool) call: input, tool,
                        outcome dict or exception, classified category,
                        latency. Written incrementally so a crash mid-run
                        doesn't lose completed results.
  results_<ts>.md     — the human-readable summary report.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.build_sample import SampleResult, build_sample
from eval.classify import CATEGORIES, classify
from permit_status_agent.tools import check_permit_status, get_inspection_history

EVAL_DIR = Path(__file__).resolve().parent
ITEM_PACING_SECONDS = 2.0  # between items — small municipal system, be a good citizen
INTRA_ITEM_PACING_SECONDS = 0.5  # between the two tool calls for the same item

FIXED_REGRESSION = [
    {"case_number": "ELEC-24-00375", "label": "fixed_regression"},
    {"case_number": "2016-8666", "label": "fixed_regression"},
]

NEGATIVE_CASES = [
    {
        "case_number": "ZZZZ-99-99999",
        "label": "negative_nonsense_permit_number",
        "expected_outcome": "not_found",
    },
    {
        "case_number": "0000 NONEXISTENT BLVD NOWHERE TX 00000",
        "label": "negative_nonsense_address",
        "expected_outcome": "not_found",
    },
    {
        "case_number": "2022-41675",
        "label": "negative_known_non_electrical",
        "expected_outcome": "not_found",
    },
]


async def run_one(tool_name: str, tool_fn, identifier: str) -> dict[str, Any]:
    start = time.monotonic()
    response: dict | None = None
    exception: BaseException | None = None
    try:
        response = await tool_fn(identifier, headless=True)
    except Exception as exc:  # noqa: BLE001 - the harness must survive a broken call
        exception = exc
    latency = time.monotonic() - start

    return {
        "tool": tool_name,
        "identifier": identifier,
        "response": response,
        "exception": f"{type(exception).__name__}: {exception}" if exception else None,
        "category": classify(response, exception),
        "latency_seconds": round(latency, 3),
    }


def build_items(sample: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for r in FIXED_REGRESSION:
        items.append({**r, "identifier": r["case_number"]})
    for r in NEGATIVE_CASES:
        items.append({**r, "identifier": r["case_number"]})
    for r in sample:
        items.append(
            {
                "case_number": r["case_number"],
                "label": "random_sample",
                "identifier": r["case_number"],
                "found_via_query": r["found_via_query"],
                "case_type": r["case_type"],
                "case_status": r["case_status"],
            }
        )
    return items


def _format_number(n: int) -> str:
    return str(n)


def write_report(
    path: Path, ts: str, sample_result: SampleResult, items: list[dict], results: list[dict]
) -> None:
    lines: list[str] = []
    lines.append(f"# Eval Results — {ts}")
    lines.append("")
    lines.append(
        f"Raw per-case data: `raw_{ts}.jsonl`  \nSample construction log: `sample_{ts}.json`"
    )
    lines.append("")

    total = len(results)
    by_category = {c: 0 for c in CATEGORIES}
    for r in results:
        by_category[r["category"]] += 1

    success_rate = (by_category["success"] / total * 100) if total else 0.0

    lines.append("## Overall")
    lines.append(f"- Total calls: {total} ({len(items)} items x 2 tools)")
    lines.append(
        f"- Success rate (outcome == \"found\"): {by_category['success']}/{total} "
        f"({success_rate:.1f}%)"
    )
    lines.append("")

    lines.append("## By category (all calls, both tools combined)")
    lines.append("| category | count | % |")
    lines.append("|---|---|---|")
    for c in CATEGORIES:
        pct = (by_category[c] / total * 100) if total else 0.0
        lines.append(f"| {c} | {by_category[c]} | {pct:.1f}% |")
    lines.append("")

    for tool in ("check_permit_status", "get_inspection_history"):
        tool_results = [r for r in results if r["tool"] == tool]
        tcount = len(tool_results)
        tby = {c: 0 for c in CATEGORIES}
        latencies = []
        for r in tool_results:
            tby[r["category"]] += 1
            latencies.append(r["latency_seconds"])

        lines.append(f"## {tool}")
        lines.append(f"- Calls: {tcount}")
        if latencies:
            lines.append(
                f"- Latency: min={min(latencies):.2f}s max={max(latencies):.2f}s "
                f"avg={sum(latencies) / len(latencies):.2f}s"
            )
        lines.append("| category | count |")
        lines.append("|---|---|")
        for c in CATEGORIES:
            if tby[c]:
                lines.append(f"| {c} | {tby[c]} |")
        lines.append("")

    lines.append("## Fixed regression cases (ELEC-24-00375, 2016-8666)")
    any_regression_fail = False
    for r in results:
        if r["item"]["label"] == "fixed_regression":
            outcome = r["response"].get("outcome") if r["response"] else "EXCEPTION"
            status = "PASS" if outcome == "found" else "FAIL"
            if status == "FAIL":
                any_regression_fail = True
            lines.append(
                f"- {r['tool']}({r['identifier']!r}) -> {outcome} [{status}] "
                f"({r['category']}, {r['latency_seconds']}s)"
            )
    lines.append("")
    lines.append(
        "**FIXED REGRESSION STATUS: "
        + ("FAIL — see above" if any_regression_fail else "ALL PASSED")
        + "**"
    )
    lines.append("")

    lines.append("## Negative / known-outcome cases")
    any_negative_fail = False
    for r in results:
        if r["item"]["label"].startswith("negative"):
            expected = r["item"].get("expected_outcome")
            actual = r["response"].get("outcome") if r["response"] else "EXCEPTION"
            status = "PASS" if actual == expected else "FAIL"
            if status == "FAIL":
                any_negative_fail = True
            lines.append(
                f"- {r['tool']}({r['identifier']!r}) expected={expected} actual={actual} "
                f"[{status}]"
            )
    lines.append("")
    lines.append(
        "**NEGATIVE CASE STATUS: "
        + ("FAIL — see above" if any_negative_fail else "ALL PASSED")
        + "**"
    )
    lines.append("")

    unexpected = [r for r in results if r["category"] == "unexpected_error"]
    lines.append(f"## unexpected_error entries ({len(unexpected)})")
    if not unexpected:
        lines.append("None.")
    else:
        for r in unexpected:
            lines.append(
                f"- {r['tool']}({r['identifier']!r}) [{r['item']['label']}]: "
                f"exception={r['exception']!r} response={r['response']!r}"
            )
    lines.append("")

    lines.append("## Sample construction (reproducibility)")
    lines.append(
        f"Fixed random seed (see eval/build_sample.py: RANDOM_SEED). Candidate pool: "
        f"{len(sample_result.candidates)} distinct electrical permits found across "
        f"{len(sample_result.log)} seed queries. Selected for this run: "
        f"{len(sample_result.sample)}."
    )
    lines.append("")
    lines.append("| query | exact_match | page_size | entities_returned | electrical_permits_found | error |")
    lines.append("|---|---|---|---|---|---|")
    for e in sample_result.log:
        lines.append(
            f"| {e.keyword} | {e.exact_match} | {e.page_size} | {e.raw_entity_count} | "
            f"{e.electrical_permit_count} | {e.error or ''} |"
        )
    lines.append("")

    status_counts: dict[str, int] = {}
    prefixed_count = 0
    plain_count = 0
    for c in sample_result.candidates:
        status_counts[c["case_status"]] = status_counts.get(c["case_status"], 0) + 1
        if "-" in c["case_number"] and c["case_number"].split("-")[0].isalpha():
            prefixed_count += 1
        else:
            plain_count += 1

    total_candidates = len(sample_result.candidates) or 1
    top_status, top_status_count = (
        max(status_counts.items(), key=lambda kv: kv[1]) if status_counts else ("n/a", 0)
    )
    top_status_pct = top_status_count / total_candidates * 100

    lines.append("### Known sample limitations (computed from this run's actual data)")
    lines.append(
        "- Status distribution across the full candidate pool ("
        + f"{len(sample_result.candidates)} permits): "
        + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items(), key=lambda kv: -kv[1]))
    )
    if top_status_pct >= 60:
        lines.append(
            f"- ⚠ Skewed: {top_status_pct:.0f}% of the candidate pool shares status "
            f"\"{top_status}\" — this sample is not representative across permit lifecycle "
            "stages, just whatever the live portal's search relevance ranking surfaced for "
            "these queries."
        )
    lines.append(
        f"- Permit-number format: {prefixed_count} prefixed (e.g. ELEC-24-00375 style), "
        f"{plain_count} plain year-sequence (e.g. 2016-8666 style) in the candidate pool."
    )
    lines.append(
        "- The candidate pool itself is bounded by 7 seed queries (1 broad + 6 street names) "
        "and PageSize caps (100/50) — this is a sample of what those specific queries surface, "
        "not an exhaustive census of every electrical permit in the system. A different set of "
        "seed queries would surface a different, possibly non-overlapping, set of permits."
    )
    lines.append(
        "- All candidates come from public search relevance ranking, which is opaque (an "
        "undocumented Tyler/EnerGov internal API) — there's no way to confirm this sample isn't "
        "systematically biased toward, say, more recently-touched or more \"popular\" records."
    )
    lines.append("")

    path.write_text("\n".join(lines))


async def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    EVAL_DIR.mkdir(exist_ok=True)

    print("Building sample from live portal...", flush=True)
    sample_result = await build_sample()

    sample_path = EVAL_DIR / f"sample_{ts}.json"
    sample_path.write_text(
        json.dumps(
            {
                "log": [dataclasses.asdict(e) for e in sample_result.log],
                "candidate_pool_size": len(sample_result.candidates),
                "candidates": sample_result.candidates,
                "selected_sample": sample_result.sample,
            },
            indent=2,
        )
    )
    print(
        f"Sample built: {len(sample_result.candidates)} distinct electrical permits found, "
        f"{len(sample_result.sample)} selected for eval. Log: {sample_path}",
        flush=True,
    )

    items = build_items(sample_result.sample)

    raw_path = EVAL_DIR / f"raw_{ts}.jsonl"
    results: list[dict[str, Any]] = []
    print(
        f"Running {len(items)} items x 2 tools = {len(items) * 2} calls, "
        f"pacing {ITEM_PACING_SECONDS}s between items...",
        flush=True,
    )
    with raw_path.open("w") as f:
        for i, item in enumerate(items, 1):
            identifier = item["identifier"]
            print(f"[{i}/{len(items)}] {item['label']}: {identifier!r}", flush=True)

            r1 = await run_one("check_permit_status", check_permit_status, identifier)
            r1["item"] = item
            f.write(json.dumps(r1) + "\n")
            f.flush()
            results.append(r1)
            print(f"    check_permit_status -> {r1['category']} ({r1['latency_seconds']}s)", flush=True)

            await asyncio.sleep(INTRA_ITEM_PACING_SECONDS)

            r2 = await run_one("get_inspection_history", get_inspection_history, identifier)
            r2["item"] = item
            f.write(json.dumps(r2) + "\n")
            f.flush()
            results.append(r2)
            print(f"    get_inspection_history -> {r2['category']} ({r2['latency_seconds']}s)", flush=True)

            await asyncio.sleep(ITEM_PACING_SECONDS)

    report_path = EVAL_DIR / f"results_{ts}.md"
    write_report(report_path, ts, sample_result, items, results)
    print(f"\nDone. Report: {report_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
