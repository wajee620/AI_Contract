"""Thin client for the GenAI Lab gateway (OpenAI-compatible).

Everything that talks to an LLM goes through here: chat, JSON-mode chat,
tool-calling chat, embeddings, and vision OCR.
"""
from __future__ import annotations
import base64
import json
import logging
import re
from typing import Any, Optional

from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)

# Corporate networks often TLS-intercept HTTPS with a root CA that lives in the
# OS trust store but not in Python's certifi bundle. truststore bridges that.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - fine on networks without interception
    pass

_client: Optional[OpenAI] = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.api_endpoint,
            api_key=settings.api_key,
            timeout=180.0,
            max_retries=2,
        )
    return _client


def chat_text(messages: list[Any], model: str | None = None,
              temperature: float = 0.1, max_tokens: int = 2048) -> str:
    if settings.mock_llm:
        from app.llm import mock
        return mock.chat_text(messages)
    resp = client().chat.completions.create(
        model=model or settings.qa_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def chat_raw(messages: list[Any], model: str | None = None, tools: list[dict] | None = None,
             temperature: float = 0.1, max_tokens: int = 2048):
    """Returns the raw assistant message (needed for tool_calls in the agent loop)."""
    if settings.mock_llm:
        from app.llm import mock
        return mock.chat_raw(messages)
    kwargs: dict[str, Any] = dict(
        model=model or settings.qa_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
    resp = client().chat.completions.create(**kwargs)
    return resp.choices[0].message


def extract_json(text: str):
    """Best-effort JSON extraction from an LLM reply (handles code fences / prose)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    for idx in sorted(starts):
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[idx:])
            return obj
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No JSON found in model reply: {text[:200]!r}")


def chat_json(messages: list[Any], model: str | None = None,
              temperature: float = 0.0, max_tokens: int = 3000):
    """Chat expecting a JSON object back. Tries native JSON mode, falls back to
    plain text + extraction, retries once on a parse failure."""
    if settings.mock_llm:
        from app.llm import mock
        return mock.chat_json(messages)
    use_model = model or settings.qa_model
    try:
        resp = client().chat.completions.create(
            model=use_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        log.debug("json_object mode unsupported/failed (%s); retrying plain", e)
        content = chat_text(messages, model=use_model, temperature=temperature, max_tokens=max_tokens)
    try:
        return extract_json(content)
    except ValueError:
        retry = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "That was not valid JSON. Reply again with ONLY the JSON object."},
        ]
        return extract_json(chat_text(retry, model=use_model, temperature=0.0, max_tokens=max_tokens))


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts (batched)."""
    if settings.mock_llm:
        from app.llm import mock
        return mock.embed(texts)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), 32):
        batch = [t[:8000] if t.strip() else " " for t in texts[i:i + 32]]
        resp = client().embeddings.create(model=settings.embed_model, input=batch)
        ordered = sorted(resp.data, key=lambda d: d.index)
        vectors.extend(d.embedding for d in ordered)
    return vectors


OCR_PROMPT = (
    "You are a precise OCR engine for legal contracts. Transcribe ALL text on this page "
    "exactly as written, top to bottom. Preserve section numbering, headings, and paragraph "
    "breaks. Do not summarize, translate, or add commentary. Output plain text only."
)


def vision_ocr(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }]
    return chat_text(messages, model=settings.ocr_model, temperature=0.0, max_tokens=4000)
