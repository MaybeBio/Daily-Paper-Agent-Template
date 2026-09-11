import os

import monitor


def test_build_issue_six_columns():
    rows_by_platform = {
        "pubmed": [
            {
                "source": "pubmed", "id": "1", "title": "A|B", "authors": "X; Y; Z; W",
                "published_date": "2026-01-01", "url": "http://orig",
            }
        ],
        "arxiv": [], "biorxiv": [], "chemrxiv": [], "medrxiv": [],
    }
    analyses = {
        ("pubmed", "1"): {
            "score": 7, "one_liner_zh": "一句话", "paper_page_path": "papers/pubmed/1/index.html"
        }
    }
    body = monitor.build_issue(rows_by_platform, "2026-01-01", "2026-01-07", analyses,
                               site_base_url="https://MaybeBio.github.io/Daily-Paper-idp-interaction-ai")
    assert "| 标题 | 作者 | 日期 | 评分 | 一句话 | 链接 |" in body
    assert "[A\\|B](http://orig)" in body
    assert "| 7 | 一句话 | [解析](https://MaybeBio.github.io/Daily-Paper-idp-interaction-ai/papers/pubmed/1/index.html) |" in body


def test_build_issue_link_falls_back_to_relative():
    rows_by_platform = {
        "pubmed": [
            {
                "source": "pubmed", "id": "1", "title": "T", "authors": "A",
                "published_date": "2026-01-01", "url": "http://orig",
            }
        ],
        "arxiv": [], "biorxiv": [], "chemrxiv": [], "medrxiv": [],
    }
    analyses = {("pubmed", "1"): {"score": 7, "one_liner_zh": "", "paper_page_path": "papers/pubmed/1/index.html"}}
    body = monitor.build_issue(rows_by_platform, "2026-01-01", "2026-01-07", analyses)
    assert "[解析](papers/pubmed/1/index.html)" in body


def test_analysis_for_missing_returns_default():
    assert monitor._analysis_for({"source": "pubmed", "id": "9"}, {})["score"] is None


def test_run_agent_pipeline_all_collects_results(monkeypatch):
    import threading
    import time

    rows = [{"source": "pubmed", "id": str(i)} for i in range(12)]
    cfg = {"llm": {"concurrency": 4}}
    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def fake_pipeline(row, cfg, out_dir, window=None):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.02)
        with lock:
            active["n"] -= 1
        i = int(row["id"])
        return {"score": i, "id": row["id"]} if i % 2 == 0 else None

    monkeypatch.setattr(monitor, "run_agent_pipeline", fake_pipeline)
    analyses = monitor.run_agent_pipeline_all(rows, cfg, "/tmp")

    assert set(analyses) == {("pubmed", str(i)) for i in range(0, 12, 2)}
    assert active["max"] > 1


def test_run_agent_pipeline_all_skips_when_llm_disabled(monkeypatch):
    calls = []

    def fake_pipeline(row, cfg, out_dir):
        calls.append(row["id"])
        return {"score": 1}

    monkeypatch.setattr(monitor, "run_agent_pipeline", fake_pipeline)
    analyses = monitor.run_agent_pipeline_all([{"source": "pubmed", "id": "1"}], {}, "/tmp")
    assert analyses == {}
    assert calls == []


def _patch_agent(monkeypatch, score, card_calls, review_calls):
    monkeypatch.setattr(monitor.fulltext, "get_fulltext", lambda *a, **k: {"text": "full", "has_fulltext": False, "fulltext_source": "abstract"})
    monkeypatch.setattr(monitor.agent, "make_client", lambda: object())
    monkeypatch.setattr(monitor.agent, "model_name", lambda: "m")
    monkeypatch.setattr(monitor.agent, "score_paper", lambda *a, **k: {"score": score, "one_liner_zh": "x"})
    monkeypatch.setattr(monitor.agent, "translate_abstract", lambda *a, **k: "译文")
    monkeypatch.setattr(monitor.agent, "build_paper_card", lambda *a, **k: card_calls.append(1) or "card")
    monkeypatch.setattr(monitor.agent, "build_review", lambda *a, **k: review_calls.append(1) or "review")


def test_run_agent_pipeline_skips_card_review_below_threshold(monkeypatch, tmp_path):
    card_calls, review_calls = [], []
    _patch_agent(monkeypatch, score=3, card_calls=card_calls, review_calls=review_calls)
    cfg = {"llm": {"min_score": 5, "enable_card": True, "enable_reviewer": True}}
    row = {"source": "pubmed", "id": "123", "doi": "10.1/x", "abstract": "The abstract.",
           "published_date": "2026-01-01", "title": "T", "authors": "A", "journal": "J", "url": "http://u"}
    analysis = monitor.run_agent_pipeline(row, cfg, str(tmp_path))
    assert analysis["score"] == 3
    assert analysis["abstract"] == "The abstract."
    assert analysis["abstract_zh"] == "译文"
    assert analysis["paper_card_path"] == ""
    assert analysis["review_path"] == ""
    assert card_calls == []
    assert review_calls == []
    assert not os.path.exists(os.path.join(str(tmp_path), "Archive", "pubmed", "2026", "01", "123", "paper-card.md"))


def test_run_agent_pipeline_generates_card_review_at_or_above_threshold(monkeypatch, tmp_path):
    card_calls, review_calls = [], []
    _patch_agent(monkeypatch, score=5, card_calls=card_calls, review_calls=review_calls)
    cfg = {"llm": {"min_score": 5, "enable_card": True, "enable_reviewer": True}}
    row = {"source": "pubmed", "id": "123", "doi": "10.1/x", "abstract": "The abstract.",
           "published_date": "2026-01-01", "title": "T", "authors": "A", "journal": "J", "url": "http://u"}
    analysis = monitor.run_agent_pipeline(row, cfg, str(tmp_path))
    assert analysis["paper_card_path"] == "paper-card.md"
    assert analysis["review_path"] == "review.md"
    assert len(card_calls) == 1
    assert len(review_calls) == 1


def test_run_agent_pipeline_writes_window_and_journal(monkeypatch, tmp_path):
    import json
    card_calls, review_calls = [], []
    _patch_agent(monkeypatch, score=7, card_calls=card_calls, review_calls=review_calls)
    cfg = {"llm": {"min_score": 5, "enable_card": True, "enable_reviewer": True}}
    row = {"source": "pubmed", "id": "123", "doi": "10.1/x", "abstract": "The abstract.",
           "published_date": "2026-01-01", "title": "T", "authors": "A", "journal": "Nature", "url": "http://u"}
    window = {"start": "2026-01-01", "end": "2026-01-07"}
    monitor.run_agent_pipeline(row, cfg, str(tmp_path), window)
    path = os.path.join(str(tmp_path), "Archive", "pubmed", "2026", "01", "123", "analysis.json")
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["journal"] == "Nature"
    assert saved["window"] == window
