#!/usr/bin/env python3
"""Generate a paper-qa corpus + citation manifest from Archive/.

For each paper under Archive/{source}/{year}/{month}/{id}/, read analysis.json
(title/authors/journal/published_date) and the raw {id}.json (DOI), export the
chosen markdown artifact(s) as .txt, and write a manifest.csv that paper-qa reads
natively (Settings.agent.index.manifest_file) to attach citation metadata — so
References render as "Smyth et al. (2026). <title>. <journal>." instead of a
filename, and in-text keys become "Smyth2026" instead of a hash.

Two non-obvious choices, both deliberate:
  * .txt not .md — paper-qa's read_doc routes .md through its *code* chunker
    (chunk_code_text); .txt uses the text chunker (chunk_text). See readers.py.
  * use_doc_details=false in the settings preset — otherwise paper-qa hydrates
    citations from Crossref/S2 at index time (network) and may overwrite the
    citation string we already have locally.

Outputs (all under --out, default paperqa_corpus/):
  *.txt                 flat text corpus = the paper_directory for `pqa index`
  manifest.csv          file_location -> citation metadata
  paperqa_settings.json Settings preset to hand to `pqa --settings`

Run after generating:
  mkdir -p ~/.pqa/settings
  cp paperqa_settings.json ~/.pqa/settings/rag.json
  export OPENAI_API_KEY="$LLM_API_KEY"          # LiteLLM key for the gateway
  pqa --settings rag index paperqa_corpus       # first run full, later incremental
  pqa --settings rag ask "Which diffusion models generate IDP ensembles?"

Usage:
  python how_to_rag/feed_paperqa.py --archive Archive --out paperqa_corpus
  python how_to_rag/feed_paperqa.py --archive Archive --out paperqa_corpus --doc-type all
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

DOC_TYPES = ("fulltext", "card", "review")
ARTIFACT = {
    "fulltext": "fulltext.md",
    "card": "paper-card.md",
    "review": "review.md",
}
MANIFEST_COLUMNS = ["file_location", "docname", "title", "doi", "year", "journal", "citation"]


def iter_paper_dirs(archive: Path):
    """Yield every Archive/{source}/{year}/{month}/{id}/ that has an analysis.json."""
    for analysis in archive.rglob("analysis.json"):
        yield analysis.parent


def safe_filename(value: str) -> str:
    """Flatten an id (PMID or DOI with slashes) into a filename-safe token."""
    text = (value or "").replace("/", "_").replace("\\", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text or "unknown"


def read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_raw_json(paper_dir: Path) -> dict | None:
    """The raw pyPaperFlow metadata JSON is the one .json file that isn't analysis.json."""
    for f in paper_dir.glob("*.json"):
        if f.name != "analysis.json":
            return read_json(f)
    return None


def find_key(obj, key: str, lower: bool = True):
    """Recursively find the first value for `key` in a nested dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == key if lower else k == key:
                if v:
                    return v
            found = find_key(v, key, lower)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_key(item, key, lower)
            if found:
                return found
    return None


def extract_doi(source: str, pid: str, raw: dict | None) -> str:
    if raw:
        doi = find_key(raw, "doi")
        if doi:
            return str(doi).strip()
    # For preprints the platform id IS the DOI (10.xxxx/...); for pubmed it's a PMID.
    if source in ("biorxiv", "medrxiv", "chemrxiv") and pid:
        return pid
    return ""


def first_author_surname(authors: str) -> str:
    first = (authors or "").split(";")[0].strip().strip(",").strip()
    if not first:
        return ""
    if "," in first:
        first = first.split(",")[0].strip()
    tokens = first.split()
    return tokens[-1].strip(".,") if tokens else first.strip(".,")


def short_authors(authors: str, limit: int = 3) -> str:
    parts = [a.strip().rstrip(".").strip() for a in (authors or "").split(";") if a.strip()]
    if not parts:
        return ""
    if len(parts) <= limit:
        return ", ".join(parts)
    return ", ".join(parts[:limit]) + ", et al"


def build_citation(authors: str, year: str, title: str, journal: str, doi: str) -> str:
    who = short_authors(authors)
    base = f"{who}. ({year}). {title}." if who else f"{title}. ({year})."
    if journal:
        base += f" {journal}."
    if doi:
        base += f" doi:{doi}"
    return base


def build_docname(authors: str, year: str, source: str, pid: str) -> str:
    surname = first_author_surname(authors)
    if surname and year:
        return f"{surname}{year}"
    return f"{source}_{pid}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--archive", default="Archive", help="Archive/ root (default: Archive)")
    ap.add_argument("--out", default="paperqa_corpus", help="flat corpus + manifest dir (default: paperqa_corpus)")
    ap.add_argument(
        "--doc-type",
        choices=("fulltext", "card", "review", "all"),
        default="fulltext",
        help="which artifact(s) to export (default: fulltext)",
    )
    ap.add_argument("--settings", default="paperqa_settings.json", help="settings preset output path")
    ap.add_argument("--llm", default=os.environ.get("LLM_MODEL", "deepseek-chat"))
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", ""))
    ap.add_argument("--embedding", default=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"))
    ap.add_argument("--force", action="store_true", help="overwrite existing corpus files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    archive = Path(args.archive)
    out = Path(args.out)
    if not archive.is_dir():
        print(f"error: archive dir not found: {archive}", file=sys.stderr)
        return 1

    types = DOC_TYPES if args.doc_type == "all" else (args.doc_type,)
    manifest_path = out / "manifest.csv"

    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)

    n_files = 0
    n_rows = 0
    manifest_rows: list[dict] = []
    with_out_files: set[str] = set()

    for paper_dir in sorted(iter_paper_dirs(archive)):
        analysis = read_json(paper_dir / "analysis.json")
        if not analysis:
            continue
        source = analysis.get("source", "")
        pid = str(analysis.get("id", ""))
        title = str(analysis.get("title", "") or "").strip()
        authors = str(analysis.get("authors", "") or "")
        journal = str(analysis.get("journal", "") or "").strip()
        pub_date = str(analysis.get("published_date", "") or "").strip()
        year = pub_date[:4]

        raw = find_raw_json(paper_dir)
        doi = extract_doi(source, pid, raw)
        citation = build_citation(authors, year, title, journal, doi)
        docname = build_docname(authors, year, source, pid)

        for t in types:
            src = paper_dir / ARTIFACT[t]
            if not src.is_file():
                continue
            # .txt so paper-qa uses the text chunker, not the code chunker.
            dst_name = f"{source}_{safe_filename(pid)}_{t}.txt"
            dst = out / dst_name
            if dst.name in with_out_files and not args.force:
                continue
            if not args.dry_run:
                shutil.copy2(src, dst)
            with_out_files.add(dst.name)
            n_files += 1
            manifest_rows.append({
                "file_location": dst_name,
                "docname": docname if t == "fulltext" else f"{docname}-{t}",
                "title": title,
                "doi": doi,
                "year": year,
                "journal": journal,
                "citation": citation,
            })
            n_rows += 1

    if not args.dry_run:
        with open(manifest_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
            w.writeheader()
            for row in manifest_rows:
                w.writerow(row)

        settings = {
            "llm": args.llm,
            "llm_config": {"base_url": args.base_url} if args.base_url else {},
            "embedding": args.embedding,
            "parsing": {"use_doc_details": False},
            "agent": {
                "index": {
                    "paper_directory": str(out.resolve()),
                    "manifest_file": "manifest.csv",
                }
            },
        }
        with open(args.settings, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    print(f"papers: {len(manifest_rows)} rows across {n_files} file(s) -> {out}")
    print(f"manifest: {manifest_path}")
    print(f"settings: {args.settings}")
    print("\nNext steps:")
    print("  mkdir -p ~/.pqa/settings")
    print(f"  cp {args.settings} ~/.pqa/settings/rag.json")
    print("  export OPENAI_API_KEY=\"$LLM_API_KEY\"")
    print(f"  pqa --settings rag index {args.out}")
    print(f"  pqa --settings rag ask \"Which diffusion models generate IDP ensembles?\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
