import json
from types import SimpleNamespace

import agent

def fake_client(responses):
    calls = []
    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            # Streaming: _chat iterates chunks and reads .choices[0].delta.content.
            def gen():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=r))])
            return gen()
    return SimpleNamespace(chat=SimpleNamespace(completions=Completions())), calls


def test_validate_score_good():
    assert agent._validate_score({"score": 7, "one_liner_zh": "x"}) == {"score": 7, "one_liner_zh": "x"}


def test_validate_score_clamps_and_coerces():
    assert agent._validate_score({"score": "9", "one_liner_zh": 3}) == {"score": 9, "one_liner_zh": "3"}


def test_score_paper_parses_json():
    client, calls = fake_client([json.dumps({"score": 5, "one_liner_zh": "一句话"})])
    res = agent.score_paper(client, "m", "title", "abstract")
    assert res == {"score": 5, "one_liner_zh": "一句话"}
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_chat_retries_then_raises():
    client, calls = fake_client([RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")])
    import pytest
    with pytest.raises(RuntimeError):
        agent._chat(client, "m", [{"role": "user", "content": "hi"}], max_attempts=2)
    assert len(calls) == 2


def test_build_paper_card_includes_meta_and_fulltext():
    client, calls = fake_client(["## 01 基本信息\n..."])
    meta = {"title": "T", "authors": "A", "journal": "J", "published_date": "2026-01-01", "doi": "10.1/x", "url": "http://u"}
    agent.build_paper_card(client, "m", "full text body", meta)
    sent = calls[0]["messages"]
    user = sent[-1]["content"]
    assert "T" in user
    assert "full text body" in user
    assert "## 01 基本信息" in sent[0]["content"]


def test_build_review_single_reviewer_structure():
    client, calls = fake_client(["## Review setup\n..."])
    agent.build_review(client, "m", "full text", {"title": "T"})
    sys_content = calls[0]["messages"][0]["content"]
    assert "## Reviewer" in sys_content
    assert "Cross-review synthesis" not in sys_content
    assert "Reviewer 2" not in sys_content


def test_translate_abstract_returns_translation():
    client, calls = fake_client(["中文译文"])
    res = agent.translate_abstract(client, "m", "The abstract in English.")
    assert res == "中文译文"
    assert "The abstract in English." in calls[0]["messages"][-1]["content"]


def test_translate_abstract_empty_abstract_returns_empty():
    client, calls = fake_client([])
    assert agent.translate_abstract(client, "m", "") == ""
    assert calls == []
