import json
import os

import build_site


def make_archive(root):
    d = os.path.join(root, "Archive", "pubmed", "2026", "09", "42437078")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "42437078.json"), "w", encoding="utf-8") as f:
        json.dump({"identity": {"title": "Paper Title", "pmid": "42437078"}, "metadata": {"entrez_date": "2026/09/01 00:00"}}, f, ensure_ascii=False)
    with open(os.path.join(d, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump({
            "title": "Paper Title",
            "authors": "Alice; Bob",
            "published_date": "2026-09-01",
            "score": 8, "one_liner_zh": "一句话", "url": "http://u",
            "paper_page_path": "papers/pubmed/42437078/index.html",
            "has_fulltext": True, "fulltext_source": "pmc",
        }, f, ensure_ascii=False)
    with open(os.path.join(d, "paper-card.md"), "w", encoding="utf-8") as f:
        f.write("## 01 基本信息\n...")
    with open(os.path.join(d, "review.md"), "w", encoding="utf-8") as f:
        f.write("## Review setup\n...")


def test_load_archive_merges(tmp_path):
    make_archive(str(tmp_path))
    papers = build_site.load_archive(str(tmp_path))
    assert len(papers) == 1
    p = papers[0]
    assert p["title"] == "Paper Title"
    assert p["score"] == 8
    assert p["paper_page_path"] == "papers/pubmed/42437078/index.html"


def test_build_site_writes_outputs(tmp_path):
    make_archive(str(tmp_path))
    out = str(tmp_path)
    build_site.build_site(out)
    assert os.path.exists(os.path.join(out, "site", "index.html"))
    assert os.path.exists(os.path.join(out, "site", "archive.html"))
    assert os.path.exists(os.path.join(out, "site", "papers", "pubmed", "42437078", "index.html"))
    assert os.path.exists(os.path.join(out, "site", "data", "index.json"))
    with open(os.path.join(out, "site", "data", "index.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data["papers"][0]["title"] == "Paper Title"


def test_score_tier():
    assert build_site.score_tier(8) == "high"
    assert build_site.score_tier(10) == "high"
    assert build_site.score_tier(7) == "mid"
    assert build_site.score_tier(5) == "mid"
    assert build_site.score_tier(4) == "low"
    assert build_site.score_tier(0) == "low"
    assert build_site.score_tier(None) == "none"
    assert build_site.score_tier("x") == "none"


def test_source_label_pubmed_journal():
    assert build_site.source_label("pubmed", "Nature") == {"venue": "Nature", "kind": "journal"}


def test_source_label_pubmed_fallback():
    assert build_site.source_label("pubmed", "") == {"venue": "PubMed", "kind": "journal"}


def test_source_label_preprint():
    assert build_site.source_label("biorxiv", "") == {"venue": "bioRxiv", "kind": "preprint"}
    assert build_site.source_label("arxiv", "") == {"venue": "arXiv", "kind": "preprint"}


def test_plain_text_strips_markdown():
    assert build_site._plain_text("**bold** and [link](http://x)") == "bold and link"


def _make_paper(root, source, sid, year, month, score, window, journal=""):
    d = os.path.join(root, "Archive", source, year, month, sid)
    os.makedirs(d, exist_ok=True)
    analysis = {
        "source": source, "id": sid, "title": f"Title {sid}", "authors": "A",
        "journal": journal, "published_date": f"{year}-{month}-02",
        "score": score, "one_liner_zh": "一句话", "abstract": "", "abstract_zh": "",
        "url": "", "has_fulltext": False, "fulltext_source": "abstract",
        "paper_page_path": f"papers/{source}/{sid}/index.html", "window": window,
    }
    with open(os.path.join(d, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f)
    return analysis


def test_load_archive_reads_window_and_journal(tmp_path):
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    papers = build_site.load_archive(str(tmp_path))
    assert len(papers) == 1
    assert papers[0]["journal"] == "Nature"
    assert papers[0]["window_start"] == "2026-09-02"
    assert papers[0]["window_end"] == "2026-09-08"


def test_load_archive_window_fallback(tmp_path):
    # published_date 2026-09-02 是周三；兜底周 = 周一 2026-08-31 ~ 周日 2026-09-06
    _make_paper(str(tmp_path), "biorxiv", "2", "2026", "09", 6, {}, journal="")
    papers = build_site.load_archive(str(tmp_path))
    assert papers[0]["window_start"] == "2026-08-31"
    assert papers[0]["window_end"] == "2026-09-06"


def test_build_search_documents(tmp_path):
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    papers = build_site.load_archive(str(tmp_path))
    head, deep = build_site._build_search_documents(papers)
    assert len(head) == 1
    assert head[0]["id"] == "pubmed:1"
    assert head[0]["url"] == "/papers/pubmed/1/index.html"
    assert "Nature" in head[0]["meta"]
    assert head[0]["summary"] == "一句话"
    assert len(deep) == 1
    assert deep[0]["id"] == "pubmed:1"
    assert deep[0]["deep"].strip() == ""


def test_build_site_writes_search_json(tmp_path):
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    build_site.build_site(str(tmp_path))
    path = os.path.join(str(tmp_path), "site", "data", "search.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["version"] == 1
    assert len(payload["documents"]) == 1
    deep_path = os.path.join(str(tmp_path), "site", "data", "search-deep.json")
    assert os.path.isfile(deep_path)
    with open(deep_path, encoding="utf-8") as f:
        deep_payload = json.load(f)
    assert deep_payload["version"] == 1
    assert len(deep_payload["documents"]) == 1


def test_build_site_end_to_end(tmp_path):
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    _make_paper(str(tmp_path), "biorxiv", "2", "2026", "09", 3,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="")
    build_site.build_site(str(tmp_path))
    site = os.path.join(str(tmp_path), "site")
    index = open(os.path.join(site, "index.html"), encoding="utf-8").read()
    assert "2026-09-02 ~ 2026-09-08" in index
    assert "score-high" in index and "score-low" in index
    assert "Nature" in index and "预印本" in index
    archive = open(os.path.join(site, "archive.html"), encoding="utf-8").read()
    assert "archive-year" in archive and "2026-09-08" in archive
    assert os.path.isfile(os.path.join(site, "weeks", "2026-09-08", "index.html"))
    assert os.path.isfile(os.path.join(site, "search.html"))
    assert os.path.isfile(os.path.join(site, "data", "search.json"))
    assert os.path.isfile(os.path.join(site, "assets", "search.js"))
    paper_html = open(os.path.join(site, "papers", "pubmed", "1", "index.html"), encoding="utf-8").read()
    assert "score-high" in paper_html


def test_site_base_path():
    assert build_site.site_base_path("https://MaybeBio.github.io/Daily-Paper-idp-interaction-ai") == "/Daily-Paper-idp-interaction-ai"
    assert build_site.site_base_path("https://user.github.io/repo/") == "/repo"
    assert build_site.site_base_path("https://user.github.io") == ""
    assert build_site.site_base_path("") == ""
    assert build_site.site_base_path(None) == ""


def test_build_site_uses_config_title_and_base(tmp_path):
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    build_site.build_site(str(tmp_path), config={
        "site_base_url": "https://x.github.io/MyTopic",
        "title": "My Topic",
        "topic": "my-topic",
    })
    index = open(os.path.join(str(tmp_path), "site", "index.html"), encoding="utf-8").read()
    assert "My Topic" in index
    with open(os.path.join(str(tmp_path), "site", "data", "search.json"), encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["documents"][0]["url"] == "/MyTopic/papers/pubmed/1/index.html"


def test_build_site_latest_window_ignores_unknown_bucket(tmp_path):
    # A real window must win over the degenerate "unknown" bucket so the
    # homepage does not fall back to an empty window_end.
    _make_paper(str(tmp_path), "pubmed", "1", "2026", "09", 8,
                {"start": "2026-09-02", "end": "2026-09-08"}, journal="Nature")
    d = os.path.join(str(tmp_path), "Archive", "pubmed", "2026", "09", "9")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump({
            "source": "pubmed", "id": "9", "title": "Title 9", "authors": "A",
            "journal": "", "published_date": "",
            "score": 6, "one_liner_zh": "一句话", "abstract": "", "abstract_zh": "",
            "url": "", "has_fulltext": False, "fulltext_source": "abstract",
            "paper_page_path": "papers/pubmed/9/index.html", "window": {},
        }, f)
    build_site.build_site(str(tmp_path))
    index = open(os.path.join(str(tmp_path), "site", "index.html"), encoding="utf-8").read()
    assert "2026-09-08" in index
    archive = open(os.path.join(str(tmp_path), "site", "archive.html"), encoding="utf-8").read()
    assert "/weeks/unknown/" not in archive
