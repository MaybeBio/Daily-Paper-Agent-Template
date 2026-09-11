"""Static site generator: walk Archive/, render Jinja2 templates into site/."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from html import unescape

import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
# templates/ lives at the repo root, one level above this scripts/ directory.
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")

PREPRINT_LABELS = {"arxiv": "arXiv", "biorxiv": "bioRxiv", "chemrxiv": "ChemRxiv", "medrxiv": "medRxiv"}


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("config must be a YAML mapping")
    return cfg


def site_base_path(site_base_url):
    """URL path prefix from site_base_url ('' -> deployed at repo root)."""
    url = (site_base_url or "").strip()
    if not url:
        return ""
    return urlparse(url).path.rstrip("/")

_TAG_RE = re.compile(r"<[^>]+>")


def score_tier(score):
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "none"
    if s >= 8:
        return "high"
    if s >= 5:
        return "mid"
    return "low"


def source_label(source, journal):
    src = (source or "").strip().lower()
    if src == "pubmed":
        venue = (journal or "").strip() or "PubMed"
        return {"venue": venue, "kind": "journal"}
    if src in PREPRINT_LABELS:
        return {"venue": PREPRINT_LABELS[src], "kind": "preprint"}
    return {"venue": (source or "unknown").strip() or "unknown", "kind": "journal"}


def _plain_text(md_text):
    rendered = _md_to_html(md_text)
    text = _TAG_RE.sub(" ", rendered).replace("\n", " ")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_date(iso):
    try:
        return dt.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return None


def _window_of(a):
    window = a.get("window") or {}
    start = window.get("start") or ""
    end = window.get("end") or ""
    if start and end:
        return start, end
    d = _parse_date(a.get("published_date", ""))
    if d:
        monday = d - dt.timedelta(days=d.weekday())
        return monday.isoformat(), (monday + dt.timedelta(days=6)).isoformat()
    return "", ""


def load_archive(out_dir: str) -> list[dict]:
    papers = []
    archive_root = os.path.join(out_dir, "Archive")
    if not os.path.isdir(archive_root):
        return papers
    for source in sorted(os.listdir(archive_root)):
        src_dir = os.path.join(archive_root, source)
        if not os.path.isdir(src_dir):
            continue
        for year in sorted(os.listdir(src_dir)):
            for month in sorted(os.listdir(os.path.join(src_dir, year))):
                for sid in sorted(os.listdir(os.path.join(src_dir, year, month))):
                    paper_dir = os.path.join(src_dir, year, month, sid)
                    analysis_path = os.path.join(paper_dir, "analysis.json")
                    if not os.path.isfile(analysis_path):
                        continue
                    with open(analysis_path, encoding="utf-8") as f:
                        a = json.load(f)
                    w_start, w_end = _window_of(a)
                    papers.append({
                        "source": source,
                        "id": a.get("id", sid),
                        "title": a.get("title", ""),
                        "authors": a.get("authors", ""),
                        "journal": a.get("journal", ""),
                        "published_date": a.get("published_date", ""),
                        "score": a.get("score"),
                        "one_liner_zh": a.get("one_liner_zh", ""),
                        "abstract": a.get("abstract", ""),
                        "abstract_zh": a.get("abstract_zh", ""),
                        "url": a.get("url", ""),
                        "has_fulltext": a.get("has_fulltext", False),
                        "fulltext_source": a.get("fulltext_source", ""),
                        "paper_page_path": a.get("paper_page_path", ""),
                        "paper_dir": paper_dir,
                        "window_start": w_start,
                        "window_end": w_end,
                    })
    papers.sort(key=lambda p: p.get("published_date") or "", reverse=True)
    return papers


def _md_to_html(text: str) -> str:
    return md.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"])


def _load_paper_md(paper_dir):
    card = review = ""
    card_path = os.path.join(paper_dir, "paper-card.md")
    review_path = os.path.join(paper_dir, "review.md")
    if os.path.isfile(card_path):
        with open(card_path, encoding="utf-8") as f:
            card = f.read()
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as f:
            review = f.read()
    return card, review


def _load_paper_files(paper_dir):
    card, review = _load_paper_md(paper_dir)
    return _md_to_html(card), _md_to_html(review)


def _build_search_documents(papers, base_path=""):
    """Split searchable fields into a small always-loaded head index and a
    larger lazily-loaded deep index (Paper Card + Review)."""
    head = []
    deep = []
    for p in papers:
        sl = source_label(p["source"], p["journal"])
        card, review = _load_paper_md(p["paper_dir"])
        doc_id = f"{p['source']}:{p['id']}"
        head.append({
            "id": doc_id,
            "title": p["title"],
            "subtitle": "",
            "url": f"{base_path}/{p['paper_page_path']}",
            "meta": [p["authors"] or "", sl["venue"], (p["published_date"] or "")[:10]],
            "tags": [],
            "summary": p["one_liner_zh"] or "",
            "abstract": " ".join([p["abstract"] or "", p["abstract_zh"] or ""]),
            "date": (p["published_date"] or "")[:10],
        })
        deep.append({
            "id": doc_id,
            "deep": " ".join([_plain_text(card), _plain_text(review)]),
        })
    return head, deep


def build_site(out_dir, config=None):
    cfg = config or {}
    base_path = site_base_path(cfg.get("site_base_url") or "")
    site_title = (cfg.get("title") or cfg.get("topic") or "").strip()
    papers = load_archive(out_dir)
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["BASE"] = base_path
    env.globals["SITE_TITLE"] = site_title
    env.globals["SEARCH_PLACEHOLDER"] = (cfg.get("search_placeholder") or "").strip()
    env.globals["score_tier"] = score_tier
    env.globals["source_label"] = source_label

    site_dir = os.path.join(out_dir, "site")
    data_dir = os.path.join(site_dir, "data")
    assets_dir = os.path.join(site_dir, "assets")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    batches = {}
    for p in papers:
        key = p["window_end"] or "unknown"
        batches.setdefault(key, []).append(p)
    for b in batches.values():
        b.sort(key=lambda x: x.get("score") if x.get("score") is not None else -1, reverse=True)

    years = {}
    for key in sorted(batches, reverse=True):
        if key == "unknown":
            continue
        ps = batches[key]
        y = key[:4]
        years.setdefault(y, []).append({"end": key, "start": ps[0]["window_start"] if ps else "", "papers": ps})

    latest_key = max((k for k in batches if k != "unknown"), default="unknown")
    this_week = batches.get(latest_key, [])
    window_start = this_week[0]["window_start"] if this_week else ""
    window_end = latest_key if latest_key != "unknown" else ""

    for p in papers:
        card_html, review_html = _load_paper_files(p["paper_dir"])
        page = env.get_template("paper.html").render(paper=p, card_html=card_html, review_html=review_html)
        page_path = os.path.join(site_dir, p["paper_page_path"])
        os.makedirs(os.path.dirname(page_path), exist_ok=True)
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(page)

    for key, ps in batches.items():
        if key == "unknown":
            continue
        page = env.get_template("week.html").render(
            window_start=ps[0]["window_start"] if ps else "",
            window_end=key,
            papers=ps,
        )
        week_dir = os.path.join(site_dir, "weeks", key)
        os.makedirs(week_dir, exist_ok=True)
        with open(os.path.join(week_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("index.html").render(
            window_start=window_start, window_end=window_end,
            papers=this_week, total=len(papers),
        ))
    with open(os.path.join(site_dir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("archive.html").render(years=years, total=len(papers)))
    with open(os.path.join(site_dir, "search.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("search.html").render())
    with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"latest_window": window_end, "papers": papers}, f, ensure_ascii=False, indent=2)
    head_docs, deep_docs = _build_search_documents(papers, base_path)
    with open(os.path.join(data_dir, "search.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "documents": head_docs}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(data_dir, "search-deep.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "documents": deep_docs}, f, ensure_ascii=False, indent=2)
    _write_assets(assets_dir)


def _write_assets(assets_dir):
    for name in ("style.css", "search.js"):
        src = os.path.join(TEMPLATES, "assets", name)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(assets_dir, name))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the static site from Archive/.")
    parser.add_argument("--out-dir", default=".", help="Repo root")
    parser.add_argument("--config", default=None, help="Path to config.yaml (for site_base_url/title)")
    args = parser.parse_args()
    cfg = load_config(args.config) if args.config else None
    build_site(args.out_dir, cfg)
