"""Full-text acquisition wrapper.

Fetches the richest available body for a paper via pyPaperFlow and falls back to
the abstract. chemrxiv has no full-text route and always degrades to abstract.
"""
from __future__ import annotations

import os


def get_fulltext(source: str, rec_id: str, doi: str, abstract: str, cfg: dict) -> dict:
    abstract = (abstract or "").strip()
    rec_id = (rec_id or "").strip()
    doi = (doi or "").strip()

    if source == "chemrxiv":
        return {"text": abstract, "has_fulltext": False, "fulltext_source": "abstract"}

    if source == "pubmed":
        text = _pubmed_full_text(rec_id)
        if text:
            return {"text": text, "has_fulltext": True, "fulltext_source": "pmc"}
        return {"text": abstract, "has_fulltext": False, "fulltext_source": "abstract"}

    if source == "arxiv":
        text = _arxiv_full_text(rec_id)
        if text:
            return {"text": text, "has_fulltext": True, "fulltext_source": "ar5iv"}
        return {"text": abstract, "has_fulltext": False, "fulltext_source": "abstract"}

    if source in ("biorxiv", "medrxiv"):
        text = _biorxiv_full_text(source, doi)
        if text:
            return {"text": text, "has_fulltext": True, "fulltext_source": "europepmc"}
        return {"text": abstract, "has_fulltext": False, "fulltext_source": "abstract"}

    return {"text": abstract, "has_fulltext": False, "fulltext_source": "abstract"}


def _pubmed_full_text(pmid: str) -> str:
    if not pmid:
        return ""
    try:
        from pyPaperFlow.pubmed.pubmed_fetcher import PubmedFetcher

        email = (os.environ.get("ENTREZ_EMAIL") or "").strip()
        api_key = os.environ.get("NCBI_API_KEY") or ""
        fetcher = PubmedFetcher(root_dir="/tmp", entrez_email=email, api_key=api_key)
        results = fetcher.fetch_pmc_full_text([pmid])
        for r in results:
            if getattr(r, "parsed_text", "").strip():
                return r.parsed_text.strip()
        return ""
    except Exception:
        return ""


def _arxiv_full_text(arxiv_id: str) -> str:
    if not arxiv_id:
        return ""
    try:
        from pyPaperFlow.preprint.arxiv_fetcher import ArxivFetcher

        return ArxivFetcher(root_dir="/tmp").fetch_full_text(arxiv_id)
    except Exception:
        return ""


def _biorxiv_full_text(platform: str, doi: str) -> str:
    if not doi:
        return ""
    try:
        from pyPaperFlow.preprint.biorxiv_fetcher import BioRxivFetcher

        return BioRxivFetcher(root_dir="/tmp", platform=platform).fetch_full_text(doi)
    except Exception:
        return ""
