"""Preflight: verify every real model behind the gateway works for its job.

Checks (one PASS/FAIL line each, with latency):
  1. embeddings  (EMBED_MODEL)   -> vector of the expected dimension
  2. Q&A model   (QA_MODEL)      -> plain chat + JSON-mode reply (rerank/judge need JSON)
  3. extraction  (EXTRACT_MODEL) -> plain chat + JSON mode + tool/function calling (Agent A)
  4. vision OCR  (OCR_MODEL)     -> reads text off a generated test image

Run before the demo:  python scripts/check_models.py
Exit code 0 only if every check passes.
"""
import os
import sys
import time

os.environ["MOCK_LLM"] = "0"  # this harness must always hit the real gateway

from app.config import settings  # noqa: E402
from app.llm import gateway  # noqa: E402

results: list[tuple[str, bool, str]] = []


def run(name: str, fn) -> None:
    t0 = time.perf_counter()
    try:
        detail = fn()
        ok = True
    except Exception as e:
        detail = f"{type(e).__name__}: {str(e)[:140]}"
        ok = False
    ms = (time.perf_counter() - t0) * 1000
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<38} {ms:7.0f} ms  {detail}")


def check_embeddings() -> str:
    vecs = gateway.embed(["contract obligation test sentence"])
    dim = len(vecs[0])
    assert dim == settings.embedding_dim, f"expected dim {settings.embedding_dim}, got {dim}"
    return f"dim={dim}"


def _chat_ok(model: str) -> str:
    out = gateway.chat_text(
        [{"role": "user", "content": "Reply with exactly the single word: ready"}],
        model=model, temperature=0.0, max_tokens=10)
    assert out.strip(), "empty reply"
    return f"reply={out.strip()[:30]!r}"


def _json_ok(model: str) -> str:
    data = gateway.chat_json(
        [{"role": "system", "content": "Reply with ONLY a JSON object."},
         {"role": "user", "content": 'Return JSON: {"status": "ok", "n": 7}'}],
        model=model, max_tokens=50)
    assert isinstance(data, dict) and data.get("status") == "ok", f"bad JSON: {data}"
    return "json-mode ok"


def check_tool_calling() -> str:
    tools = [{
        "type": "function",
        "function": {
            "name": "get_clause",
            "description": "Fetch a contract clause by id",
            "parameters": {"type": "object",
                           "properties": {"clause_id": {"type": "string"}},
                           "required": ["clause_id"]},
        },
    }]
    msg = gateway.chat_raw(
        [{"role": "user", "content": "Fetch clause abc-42 using the tool provided."}],
        model=settings.extract_model, tools=tools, max_tokens=100)
    assert msg.tool_calls, "model returned no tool_calls"
    call = msg.tool_calls[0]
    assert call.function.name == "get_clause", f"unexpected tool: {call.function.name}"
    return f"tool_call={call.function.name}({call.function.arguments.strip()[:40]})"


def check_vision_ocr() -> str:
    import fitz  # render a small test image with known text — no extra deps

    doc = fitz.open()
    page = doc.new_page(width=400, height=120)
    page.insert_text((20, 60), "SECTION 7 DATA PROTECTION", fontsize=20)
    png = page.get_pixmap(dpi=150).tobytes("png")
    doc.close()
    text = gateway.vision_ocr(png)
    assert "data protection" in text.lower() or "section 7" in text.lower(), \
        f"OCR text did not contain expected words: {text[:80]!r}"
    return f"read={text.strip()[:40]!r}"


print(f"gateway: {settings.api_endpoint}   key: {settings.api_key[:6]}...{settings.api_key[-4:]}")
print(f"== embeddings: {settings.embed_model}")
run("embed -> 3072-dim vector", check_embeddings)
print(f"== Q&A / rerank / judge: {settings.qa_model}")
run("qa chat", lambda: _chat_ok(settings.qa_model))
run("qa json mode", lambda: _json_ok(settings.qa_model))
print(f"== extraction + agent: {settings.extract_model}")
run("extract chat", lambda: _chat_ok(settings.extract_model))
run("extract json mode", lambda: _json_ok(settings.extract_model))
run("agent tool calling", check_tool_calling)
print(f"== vision OCR: {settings.ocr_model}")
run("vision OCR reads test image", check_vision_ocr)

failed = [n for n, ok, _ in results if not ok]
print(f"\n================ MODELS: {len(results) - len(failed)}/{len(results)} checks passed ================")
if failed:
    print("failed:", ", ".join(failed))
sys.exit(1 if failed else 0)
