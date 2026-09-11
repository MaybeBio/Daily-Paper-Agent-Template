"""LLM agent layer: OpenAI-compatible client + prompt builders."""
from __future__ import annotations

import json
import os
import random
import time

import yaml
from openai import OpenAI

DEFAULT_MODEL = "deepseek-chat"
MAX_INPUT_CHARS = 180_000  # keep comfortably inside a 256k-token context


def _load_prompts() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for key in ("score", "translate", "paper_card", "review"):
        if not data.get(key, {}).get("system"):
            raise ValueError(f"prompts.yaml 缺少 '{key}.system'")
    return data


_PROMPTS = _load_prompts()
SCORE_SYSTEM = _PROMPTS["score"]["system"]
TRANSLATE_SYSTEM = _PROMPTS["translate"]["system"]
PAPER_CARD_SYSTEM = _PROMPTS["paper_card"]["system"]
REVIEWER_SYSTEM = _PROMPTS["review"]["system"]


def make_client() -> OpenAI:
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    kwargs = {"api_key": api_key, "timeout": 180.0}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def model_name() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2) :]
    return head + "\n\n[内容过长，中间已省略]\n\n" + tail


def _chat(client, model, messages, temperature=0.0, max_tokens=8000, json_mode=False, max_attempts=4):
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                # Stream so the read timeout resets on every chunk. Non-streaming,
                # the gateway buffers the whole 16k-token card/review and returns it
                # at once; a slow gateway (~190s) then trips the client timeout.
                "stream": True,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            parts: list[str] = []
            for chunk in client.chat.completions.create(**kwargs):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    parts.append(delta.content)
            return "".join(parts).strip()
        except Exception as exc:  # noqa: BLE001 — retry any transport/parse failure
            last = exc
            if attempt + 1 < max_attempts:
                time.sleep(min(30.0, 2 ** attempt + random.random()))
    raise RuntimeError(f"LLM call failed after {max_attempts} attempts: {last}")


def _validate_score(obj: dict) -> dict:
    raw_score = obj.get("score", 0)
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))
    one_liner = str(obj.get("one_liner_zh", "") or "").strip()
    return {"score": score, "one_liner_zh": one_liner}


def score_paper(client, model, title: str, abstract: str) -> dict:
    user = f"标题：{title}\n\n摘要：{abstract or '（无摘要）'}"
    raw = _chat(
        client,
        model,
        [
            {"role": "system", "content": SCORE_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=500,
        json_mode=True,
    )
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = {}
    return _validate_score(obj)


def translate_abstract(client, model, abstract: str) -> str:
    abstract = (abstract or "").strip()
    if not abstract:
        return ""
    return _chat(
        client,
        model,
        [
            {"role": "system", "content": TRANSLATE_SYSTEM},
            {"role": "user", "content": abstract},
        ],
        temperature=0.0,
        max_tokens=2000,
    )


def _meta_block(meta: dict) -> str:
    return "\n".join(
        [
            f"标题：{meta.get('title', '')}",
            f"作者：{meta.get('authors', '')}",
            f"期刊/平台：{meta.get('journal', '')}",
            f"日期：{meta.get('published_date', '')}",
            f"DOI/ID：{meta.get('doi', '') or meta.get('id', '')}",
            f"URL：{meta.get('url', '')}",
        ]
    )


def build_paper_card(client, model, fulltext: str, meta: dict) -> str:
    user = f"{_meta_block(meta)}\n\n--- 正文（全文或摘要）---\n\n{_truncate(fulltext)}"
    return _chat(
        client,
        model,
        [
            {"role": "system", "content": PAPER_CARD_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=16000,
    )


def build_review(client, model, fulltext: str, meta: dict) -> str:
    user = f"{_meta_block(meta)}\n\n--- 正文（全文或摘要）---\n\n{_truncate(fulltext)}"
    return _chat(
        client,
        model,
        [
            {"role": "system", "content": REVIEWER_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=12000,
    )
