#!/usr/bin/env python3
"""Backfill historical weeks by driving monitor.py once per historical run-date.

Each week gets its own monitor run whose window ends on that week's Sunday, so
papers land in their own publication week on the site (the same week key the
weekly cron produces) and no single fetch runs into PubMed's retmax=500 or
arXiv's max_results cap — a multi-year window would silently blow past both.

    python scripts/backfill.py --since 2025-09-15 --until 2026-09-14 --dry-run
    python scripts/backfill.py --since 2025-09-15 --until 2026-09-14

Exits non-zero and lists the affected weeks if any week crashed or finished
with one or more platforms missing (monitor.py itself exits 0 on a partial
failure, so a week can silently lack e.g. all PubMed results).
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
MONITOR = os.path.join(HERE, "monitor.py")
WINDOW_DAYS = 7
RETRY_CMD = "python scripts/backfill.py"
PREFLIGHT_TIMEOUT = 15.0

# monitor.py's closing stderr lines on a partial or lossy run, e.g.
#   Warning: 1 platform(s) failed: ['pubmed']
#   Warning: 1 platform(s) degraded: ['biorxiv']
# Matching these lines rather than the per-platform "[pubmed] FAILED:" /
# "[biorxiv] DEGRADED:" lines keeps per-paper "[agent] ... FAILED:" (one paper's
# LLM call died) out of the platform-failure count.
_PLATFORM_FAILURES = re.compile(r"Warning: \d+ platform\(s\) failed: (\[.*\])\s*$", re.MULTILINE)

# A fetcher that loses Europe PMC falls back to Crossref-only and *keeps going*,
# so monitor.py never counts it as a failure. It is not equivalent: Crossref
# cannot do boolean groups, so the query degrades to a lossy superset.
_PLATFORM_DEGRADED = re.compile(r"Warning: \d+ platform\(s\) degraded: (\[.*\])\s*$", re.MULTILINE)

# One paper's LLM pipeline died (e.g. 429 rate limit): its metadata + fulltext
# are archived but analysis.json never gets written. monitor.py exits 0, so this
# line is the only trace that the week is missing LLM artifacts.
_AGENT_FAILED = re.compile(r"Warning: \d+ paper\(s\) agent-failed: (\[.*\])\s*$", re.MULTILINE)


def monday_run_dates(since: str, until: str) -> list[str]:
    """Every Monday in [since, until] as ISO dates.

    A Monday run-date D yields the window [D-7, D-1] — one calendar week ending
    on the preceding Sunday.
    """
    start = dt.date.fromisoformat(since)
    end = dt.date.fromisoformat(until)
    if end < start:
        return []
    day = start + dt.timedelta(days=(-start.weekday()) % 7)
    out = []
    while day <= end:
        out.append(day.isoformat())
        day += dt.timedelta(days=7)
    return out


def week_args(run_date: str, config: str, out_dir: str, platforms: str | None = None) -> list[str]:
    args = [
        "--config", config,
        "--out-dir", out_dir,
        "--run-date", run_date,
        "--window-days", str(WINDOW_DAYS),
    ]
    if platforms:
        args += ["--platforms", platforms]
    return args


def _platforms_list(platforms: str | None) -> list[str] | None:
    """Parse a comma-separated --platforms value, or None when unset."""
    if not platforms:
        return None
    return [p.strip() for p in platforms.split(",") if p.strip()]


def missing_env(platforms: list[str] | None = None) -> list[str]:
    """Env vars this run needs.

    LLM_API_KEY is always required — every platform runs the LLM pipeline.
    ENTREZ_EMAIL is only needed when pubmed is among the platforms.
    """
    required = []
    if platforms is None or "pubmed" in platforms:
        required.append("ENTREZ_EMAIL")
    required.append("LLM_API_KEY")
    return [name for name in required if not (os.environ.get(name) or "").strip()]


def probe_targets(platforms: list[str] | None = None) -> list[tuple[str, str, dict]]:
    """(label, url, headers) for the external services this run depends on."""
    llm_base = (os.environ.get("LLM_BASE_URL") or "").strip() or "https://api.openai.com/v1"
    llm_key = (os.environ.get("LLM_API_KEY") or "").strip()
    targets: list[tuple[str, str, dict]] = []
    if platforms is None or "pubmed" in platforms:
        targets.append(("NCBI eutils", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi", {}))
    if platforms is None or "biorxiv" in platforms or "medrxiv" in platforms:
        targets.append(("Europe PMC", "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=SRC%3APPR&format=json&pageSize=1", {}))
    if platforms is None or "arxiv" in platforms:
        targets.append(("arXiv", "https://export.arxiv.org/api/query?search_query=all:electron&max_results=1", {}))
    # LLM gateway is probed for every run: all platforms go through the LLM pipeline.
    targets.append(("LLM gateway", llm_base.rstrip("/") + "/models", {"Authorization": f"Bearer {llm_key}"}))
    return targets


def _check_target(target: tuple[str, str, dict], timeout: float) -> str | None:
    """None when the service answered, else a one-line reason it did not.

    Any answer counts as reachable — a gateway may not expose /models at all, and
    a 404 still proves the connection and the proxy path work. Only a 5xx, a
    rejected key, a 406 (the server refuses to serve — arXiv's export API returns
    this during outages), or no response at all means the run would be wasted.
    """
    label, url, headers = target
    try:
        response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    except Exception as exc:
        return f"{label}: {type(exc).__name__}"
    if response.status_code >= 500 or response.status_code in (401, 403, 406):
        return f"{label}: HTTP {response.status_code}"
    return None


def preflight(platforms: list[str] | None = None, timeout: float = PREFLIGHT_TIMEOUT) -> list[str]:
    """Probe each needed service once and return a message per broken one.

    Runs before the first week so a dead network — typically a fresh tmux pane
    that never inherited http_proxy from ~/.zshrc — costs seconds, not hours.
    """
    targets = probe_targets(platforms)
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        problems = list(pool.map(lambda t: _check_target(t, timeout), targets))
    for (label, _, _), problem in zip(targets, problems):
        print(f"  [{'FAIL' if problem else ' ok '}] {label:<12} {problem or ''}")
    return [problem for problem in problems if problem]


def _summary_platforms(pattern: re.Pattern, stderr: str) -> list[str]:
    match = pattern.search(stderr)
    if not match:
        return []
    try:
        names = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        return []
    return list(names) if isinstance(names, list) else []


def week_failures(stderr: str) -> list[str]:
    """Platforms monitor.py reported as failed for one week, from its stderr.

    monitor.py exits 0 when only some platforms fail, so a week can finish with
    a hole in its coverage — this is how backfill.py notices.
    """
    return _summary_platforms(_PLATFORM_FAILURES, stderr)


def week_degradations(stderr: str) -> list[str]:
    """Platforms that fell back to a lossy source instead of failing outright."""
    return _summary_platforms(_PLATFORM_DEGRADED, stderr)


def week_agent_failures(stderr: str) -> list[str]:
    """"source/id" of papers whose LLM pipeline failed, from monitor.py's stderr.

    These papers keep metadata + fulltext but lack analysis.json, so the week is
    incomplete even though monitor.py exits 0.
    """
    return _summary_platforms(_AGENT_FAILED, stderr)


def retry_commands(weeks: list[str]) -> list[str]:
    """One command per week, so retrying doesn't re-run the weeks in between."""
    return [f"{RETRY_CMD} --since {w} --until {w}" for w in weeks]


def run_week(run_date: str, config: str, out_dir: str, platforms: str | None = None) -> tuple[int, str]:
    """Run monitor.py for one week, returning (exit code, captured stderr).

    stderr is echoed back out as it arrives — a week takes minutes to hours and
    the run must stay observable, so it is piped-and-tee'd rather than
    swallowed with capture_output.
    """
    proc = subprocess.Popen(
        [sys.executable, MONITOR] + week_args(run_date, config, out_dir, platforms),
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    captured = []
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        captured.append(line)
    return proc.wait(), "".join(captured)


def parse_args():
    p = argparse.ArgumentParser(description="Backfill historical weeks via monitor.py.")
    p.add_argument("--since", required=True, help="Earliest run-date (YYYY-MM-DD); snapped forward to a Monday")
    p.add_argument("--until", required=True, help="Latest run-date (YYYY-MM-DD); snapped back to a Monday")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--out-dir", default=".")
    p.add_argument("--platforms", default=None, help="Comma-separated platforms to backfill (default: all configured)")
    p.add_argument("--dry-run", action="store_true", help="Print the week plan and exit")
    return p.parse_args()


def _window(run_date: str) -> str:
    d = dt.date.fromisoformat(run_date)
    return f"{(d - dt.timedelta(days=WINDOW_DAYS)).isoformat()} .. {(d - dt.timedelta(days=1)).isoformat()}"


def main():
    args = parse_args()
    weeks = monday_run_dates(args.since, args.until)
    if not weeks:
        print(f"No Monday in {args.since} .. {args.until}; nothing to do.", file=sys.stderr)
        return 1

    first = dt.date.fromisoformat(weeks[0]) - dt.timedelta(days=WINDOW_DAYS)
    last = dt.date.fromisoformat(weeks[-1]) - dt.timedelta(days=1)
    print(f"{len(weeks)} week(s), covering {first} .. {last}")
    if args.dry_run:
        for w in weeks:
            print(f"  run-date {w}  ->  window {_window(w)}")
        return 0

    platform_list = _platforms_list(args.platforms)

    missing = missing_env(platform_list)
    if missing:
        print(f"Missing env var(s): {', '.join(missing)}. Refusing to start.", file=sys.stderr)
        return 1

    print("Pre-flight:", flush=True)
    unreachable = preflight(platform_list)
    if unreachable:
        print(f"\n{len(unreachable)} service(s) unreachable. Nothing was fetched.", file=sys.stderr)
        print("A fresh tmux pane usually lacks the proxy — check that http_proxy /", file=sys.stderr)
        print("https_proxy are exported in this shell before re-running.", file=sys.stderr)
        return 1

    problems: dict[str, list[str]] = {}
    for i, week in enumerate(weeks, 1):
        print(f"[{i}/{len(weeks)}] run-date {week}  window {_window(week)}", flush=True)
        rc, stderr = run_week(week, args.config, args.out_dir, args.platforms)

        reasons = []
        if rc != 0:
            reasons.append(f"crashed (exit {rc})")
        else:
            # monitor.py exits 0 in both of these cases, so the log is the only
            # evidence that the week came back with less than it should have.
            failed = week_failures(stderr)
            if failed:
                reasons.append(f"no results from: {', '.join(failed)}")
            degraded = week_degradations(stderr)
            if degraded:
                reasons.append(f"degraded to Crossref-only: {', '.join(degraded)}")
            agent_failed = week_agent_failures(stderr)
            if agent_failed:
                reasons.append(f"LLM failed for {len(agent_failed)} paper(s): {', '.join(agent_failed)}")

        if reasons:
            problems[week] = reasons
            print(f"[{i}/{len(weeks)}] {week} PROBLEM — {'; '.join(reasons)}", file=sys.stderr, flush=True)

    if problems:
        print(f"\n{len(problems)} of {len(weeks)} week(s) need attention:", file=sys.stderr)
        for week in sorted(problems):
            print(f"  {week}  {'; '.join(problems[week])}", file=sys.stderr)
        print("\nRe-run these weeks (a repeat week re-runs its LLM work too):", file=sys.stderr)
        for cmd in retry_commands(sorted(problems)):
            print(f"  {cmd}", file=sys.stderr)
        return 1

    print(f"\nAll {len(weeks)} week(s) done. Now run: python scripts/build_site.py --out-dir . --config config.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
