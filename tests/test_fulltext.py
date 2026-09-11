import fulltext as ft


def test_get_fulltext_chemrxiv_abstract_only():
    res = ft.get_fulltext("chemrxiv", "10.26434/x", "10.26434/x", "The abstract.", {})
    assert res == {"text": "The abstract.", "has_fulltext": False, "fulltext_source": "abstract"}


def test_get_fulltext_arxiv_calls_ar5iv(monkeypatch):
    def fake_fetch(self, arxiv_id):
        assert arxiv_id == "2301.00001"
        return "## Intro\nbody text"
    monkeypatch.setattr("pyPaperFlow.preprint.arxiv_fetcher.ArxivFetcher.fetch_full_text", fake_fetch)
    res = ft.get_fulltext("arxiv", "2301.00001", "", "abs", {})
    assert res["has_fulltext"] is True
    assert res["fulltext_source"] == "ar5iv"
    assert "body text" in res["text"]


def test_get_fulltext_arxiv_empty_falls_back(monkeypatch):
    monkeypatch.setattr(
        "pyPaperFlow.preprint.arxiv_fetcher.ArxivFetcher.fetch_full_text",
        lambda self, arxiv_id: "",
    )
    res = ft.get_fulltext("arxiv", "2301.00001", "", "the abstract", {})
    assert res == {"text": "the abstract", "has_fulltext": False, "fulltext_source": "abstract"}


def test_get_fulltext_pubmed_calls_pmc(monkeypatch):
    class FakeText:
        parsed_text = "## Methods\nfull methods text"
    def fake_pmc(self, pmid_list, output_dir=None, pmid_year_map=None):
        assert pmid_list == ["12345678"]
        return [FakeText()]
    monkeypatch.setattr("pyPaperFlow.pubmed.pubmed_fetcher.PubmedFetcher.fetch_pmc_full_text", fake_pmc)
    res = ft.get_fulltext("pubmed", "12345678", "", "abs", {})
    assert res["has_fulltext"] is True
    assert res["fulltext_source"] == "pmc"
