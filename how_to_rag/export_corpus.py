#!/usr/bin/env python3
"""Export Archive/ into a flat, RAG-ready corpus of markdown/text files.

Archive/{source}/{year}/{month}/{id}/ holds {id}.json, fulltext.md, analysis.json,
paper-card.md, review.md. All five RAG tools (ragflow / mcp-local-rag / anything-llm
/ paper-qa / dify) consume a flat list of files, so this flattens the nested layout
into {source}_{id}_{doctype}.{ext}.

Why --ext txt exists: paper-qa's read_doc routes .md through its *code* chunker
(chunk_code_text), while .txt uses the text chunker (chunk_text). Exporting the
full text as .txt keeps paper-qa on the text path.

Usage:
  python how_to_rag/export_corpus.py --archive Archive --out corpus_flat
  python how_to_rag/export_corpus.py --archive Archive --out corpus_flat \
      --doc-type all --ext txt
  python how_to_rag/export_corpus.py --archive Archive --out corpus_flat \
      --mode symlink --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DOC_TYPES = ("fulltext", "card", "review")
ARTIFACT = {
    "fulltext": "fulltext.md",
    "card": "paper-card.md",
    "review": "review.md",
}


def iter_paper_dirs(archive: Path):
    for artifact in archive.rglob("fulltext.md"):
        yield artifact.parent


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--archive", default="Archive", help="Archive/ root (default: Archive)")
    ap.add_argument("--out", default="corpus_flat", help="flat output dir (default: corpus_flat)")
    ap.add_argument(
        "--doc-type",
        choices=("fulltext", "card", "review", "all"),
        default="fulltext",
        help="which artifact(s) to export (default: fulltext)",
    )
    ap.add_argument(
        "--ext", choices=("md", "txt"), default="md",
        help="output extension; use txt for paper-qa (default: md)",
    )
    ap.add_argument("--mode", choices=("copy", "symlink"), default="copy")
    ap.add_argument("--force", action="store_true", help="overwrite existing output files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    archive = Path(args.archive)
    out = Path(args.out)
    if not archive.is_dir():
        print(f"error: archive dir not found: {archive}", file=sys.stderr)
        return 1

    types = DOC_TYPES if args.doc_type == "all" else (args.doc_type,)

    n = 0
    for paper_dir in iter_paper_dirs(archive):
        parts = paper_dir.relative_to(archive).parts  # (source, year, month, id)
        source = parts[0]
        pid = parts[-1] if len(parts) >= 4 else paper_dir.name
        for t in types:
            src = paper_dir / ARTIFACT[t]
            if not src.is_file():
                continue
            dst = out / f"{source}_{pid}_{t}.{args.ext}"
            if dst.exists() and not args.force:
                continue
            if args.dry_run:
                print(f"[dry-run] {src} -> {dst}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if args.mode == "symlink":
                    if dst.exists() or dst.is_symlink():
                        dst.unlink()
                    dst.symlink_to(src.resolve())
                else:
                    shutil.copy2(src, dst)
            n += 1

    print(f"exported {n} file(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
