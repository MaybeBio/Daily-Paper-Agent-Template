import httpx
import pytest
import requests

import backfill
import monitor


def test_monday_run_dates_returns_only_mondays():
    assert backfill.monday_run_dates("2026-09-01", "2026-09-30") == [
        "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28",
    ]


def test_monday_run_dates_includes_both_ends():
    assert backfill.monday_run_dates("2026-09-14", "2026-09-14") == ["2026-09-14"]


def test_monday_run_dates_empty_when_range_has_no_monday():
    # 2026-09-15 (Tue) .. 2026-09-18 (Fri)
    assert backfill.monday_run_dates("2026-09-15", "2026-09-18") == []


def test_monday_run_dates_empty_when_until_precedes_since():
    assert backfill.monday_run_dates("2026-09-14", "2026-09-01") == []


def test_monday_run_dates_covers_one_year():
    assert len(backfill.monday_run_dates("2025-09-15", "2026-09-14")) == 53


def test_week_args_uses_a_whole_week_window():
    args = backfill.week_args("2026-09-14", "config.yaml", ".")
    assert args[args.index("--run-date") + 1] == "2026-09-14"
    assert args[args.index("--window-days") + 1] == "7"


def test_week_args_never_asks_for_an_issue():
    args = backfill.week_args("2026-09-14", "config.yaml", ".")
    assert "--issue-body" not in args
    assert "--issue-title" not in args


def test_week_args_omits_platforms_by_default():
    args = backfill.week_args("2026-09-14", "config.yaml", ".")
    assert "--platforms" not in args


def test_week_args_passes_platforms_through():
    args = backfill.week_args("2026-09-14", "config.yaml", ".", "arxiv")
    assert args[args.index("--platforms") + 1] == "arxiv"


def test_missing_env_lists_absent_vars(monkeypatch):
    monkeypatch.delenv("ENTREZ_EMAIL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert backfill.missing_env() == ["ENTREZ_EMAIL", "LLM_API_KEY"]


def test_missing_env_ignores_blank_values(monkeypatch):
    monkeypatch.setenv("ENTREZ_EMAIL", "  ")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    assert backfill.missing_env() == ["ENTREZ_EMAIL"]


def test_missing_env_skips_entrez_email_for_arxiv_only(monkeypatch):
    monkeypatch.delenv("ENTREZ_EMAIL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert backfill.missing_env(["arxiv"]) == ["LLM_API_KEY"]


def test_missing_env_requires_entrez_email_for_pubmed(monkeypatch):
    monkeypatch.delenv("ENTREZ_EMAIL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert backfill.missing_env(["pubmed"]) == ["ENTREZ_EMAIL", "LLM_API_KEY"]


def test_week_failures_reads_platforms_from_the_summary_line():
    log = "[pubmed] FAILED: RemoteDisconnected\nWarning: 1 platform(s) failed: ['pubmed']\n"
    assert backfill.week_failures(log) == ["pubmed"]


def test_week_failures_handles_several_platforms():
    log = "Warning: 2 platform(s) failed: ['arxiv', 'pubmed']\n"
    assert backfill.week_failures(log) == ["arxiv", "pubmed"]


def test_week_failures_empty_on_a_clean_run():
    assert backfill.week_failures("[pubmed] 12 records (archived 12)\n") == []


def test_week_failures_ignores_per_paper_agent_failures():
    # [agent] FAILED lines mean one paper's LLM call died, not that a platform
    # went down — the week is still complete.
    log = "[agent] pubmed/42723155 FAILED: 429 rate limited\n"
    assert backfill.week_failures(log) == []


def test_retry_commands_pin_each_week_to_itself():
    assert backfill.retry_commands(["2026-03-02", "2026-09-14"]) == [
        "python scripts/backfill.py --since 2026-03-02 --until 2026-03-02",
        "python scripts/backfill.py --since 2026-09-14 --until 2026-09-14",
    ]


# Verbatim shape of a degraded week: monitor.py prints a per-platform reason line
# and a closing summary line. backfill.py reads only the summary line.
_DEGRADED_LOG = (
    "[biorxiv] DEGRADED: Europe PMC unavailable (HTTP 503)\n"
    "[biorxiv] 2 records (archived 2)\n"
    "Warning: 1 platform(s) degraded: ['biorxiv']\n"
)


def test_week_degradations_reads_platforms_from_the_summary_line():
    assert backfill.week_degradations(_DEGRADED_LOG) == ["biorxiv"]


def test_week_degradations_handles_several_platforms():
    log = "Warning: 2 platform(s) degraded: ['biorxiv', 'medrxiv']\n"
    assert backfill.week_degradations(log) == ["biorxiv", "medrxiv"]


def test_week_degradations_empty_on_a_clean_run():
    assert backfill.week_degradations("[biorxiv] 2 records (archived 2)\n") == []


def test_week_degradations_ignores_a_per_platform_reason_line():
    # Only the summary line counts; a reason line without it (e.g. monitor.py
    # died mid-run) must not be mistaken for a completed degraded week.
    assert backfill.week_degradations("[biorxiv] DEGRADED: Europe PMC unavailable (HTTP 503)\n") == []


def test_week_degradations_ignores_an_outright_platform_failure():
    log = "[biorxiv] FAILED: connection refused\nWarning: 1 platform(s) failed: ['biorxiv']\n"
    assert backfill.week_degradations(log) == []


def test_week_failures_ignores_a_degraded_summary():
    log = "Warning: 1 platform(s) degraded: ['biorxiv']\n"
    assert backfill.week_failures(log) == []


# monitor.py writes these lines and backfill.py reads them, so the two scripts
# share a stderr format. Build the fixtures from monitor's own formatter instead
# of hand-copying the text — a copy stays green after monitor's wording changes.
def test_week_failures_parses_monitors_own_summary_line():
    line = monitor.platform_summary_line("failed", ["pubmed", "arxiv"])
    assert backfill.week_failures(line + "\n") == ["pubmed", "arxiv"]


def test_week_degradations_parses_monitors_own_summary_line():
    line = monitor.platform_summary_line("degraded", ["biorxiv"])
    assert backfill.week_degradations(line + "\n") == ["biorxiv"]


def _labels(platforms=None):
    return [label for label, _, _ in backfill.probe_targets(platforms)]


def test_probe_targets_covers_every_external_service(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_BASE_URL", "https://gw.example/v1")
    assert _labels() == ["NCBI eutils", "Europe PMC", "arXiv", "LLM gateway"]


def test_probe_targets_joins_the_gateway_url_without_doubling_slashes(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("LLM_BASE_URL", "https://gw.example/v1/")
    _, url, headers = backfill.probe_targets()[-1]
    assert url == "https://gw.example/v1/models"
    assert headers["Authorization"] == "Bearer sk-secret"


def test_probe_targets_falls_back_to_the_openai_default(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert backfill.probe_targets()[-1][1] == "https://api.openai.com/v1/models"


def test_probe_targets_filters_to_arxiv_plus_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    assert _labels(["arxiv"]) == ["arXiv", "LLM gateway"]


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_check_target_flags_an_unhealthy_status(monkeypatch):
    monkeypatch.setattr(backfill.httpx, "get", lambda *a, **k: _FakeResponse(503))
    assert backfill._check_target(("Europe PMC", "http://x", {}), 1.0) == "Europe PMC: HTTP 503"


def test_check_target_accepts_a_404(monkeypatch):
    # A gateway that does not expose /models still proves it is reachable by answering.
    monkeypatch.setattr(backfill.httpx, "get", lambda *a, **k: _FakeResponse(404))
    assert backfill._check_target(("LLM gateway", "http://x", {}), 1.0) is None


def test_check_target_flags_a_rejected_key(monkeypatch):
    monkeypatch.setattr(backfill.httpx, "get", lambda *a, **k: _FakeResponse(401))
    assert backfill._check_target(("LLM gateway", "http://x", {}), 1.0) == "LLM gateway: HTTP 401"


def test_check_target_flags_a_406(monkeypatch):
    # arXiv's export API returns 406 during outages; a reachable-but-refusing
    # endpoint must not pass the preflight as healthy.
    monkeypatch.setattr(backfill.httpx, "get", lambda *a, **k: _FakeResponse(406))
    assert backfill._check_target(("arXiv", "http://x", {}), 1.0) == "arXiv: HTTP 406"


def test_arxiv_total_results_raises_instead_of_swallowing(monkeypatch):
    # A transport error must propagate (so arxiv is marked failed), not collapse
    # into a silent 0-result week.
    monkeypatch.setattr(monitor.time, "sleep", lambda s: None)

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(monitor.requests, "get", boom)
    with pytest.raises(requests.exceptions.ConnectionError):
        monitor._arxiv_total_results("all:electron")


def test_check_target_reports_a_connection_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(backfill.httpx, "get", boom)
    assert backfill._check_target(("NCBI eutils", "http://x", {}), 1.0) == "NCBI eutils: ConnectError"


def test_preflight_is_empty_when_every_service_answers(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setattr(backfill, "_check_target", lambda target, timeout: None)
    assert backfill.preflight() == []


def test_preflight_names_the_broken_services_in_target_order(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setattr(
        backfill, "_check_target",
        lambda target, timeout: None if target[0] == "arXiv" else f"{target[0]}: ConnectError",
    )
    assert backfill.preflight() == [
        "NCBI eutils: ConnectError",
        "Europe PMC: ConnectError",
        "LLM gateway: ConnectError",
    ]
