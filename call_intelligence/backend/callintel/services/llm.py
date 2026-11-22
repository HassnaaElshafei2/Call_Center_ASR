"""Client for the models on the DGX gateway (Open WebUI, OpenAI-compatible, under /api).

Qwen3.6 reasons before answering unless told not to; every call here sends enable_thinking=false so answers are
fast and the token budget goes to the answer.
"""
import json
import logging
import time

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _headers():
    key = settings().llm_api_key
    if not key:
        raise LLMError("LLM_API_KEY is not set")
    if not key.isascii() or " " in key:
        raise LLMError("LLM_API_KEY isn't a valid key: it contains characters like • or spaces (a key copied from a "
                       "display that hides secrets?). Paste the full key into .env, then run: docker compose up -d")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def chat(messages: list[dict], *, model: str | None = None, max_tokens: int = 2000, temperature: float = 0.1,
         json_schema: dict | None = None, json_mode: bool = False, tools: list[dict] | None = None,
         retries: int = 2, timeout: float | None = None, repetition_penalty: float | None = None) -> dict:
    """One chat completion; returns the assistant message (content, tool_calls).
    json_schema is accepted for short outputs only (see chat_json); json_mode asks for any JSON object."""
    body = {"model": model or settings().llm_model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
    if repetition_penalty:
        body["repetition_penalty"] = repetition_penalty         # vLLM: discourages a word repeated in a loop
    if json_schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "strict": True,
                                                                          "schema": json_schema}}
    elif json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
    last = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(f"{settings().llm_api_url}/chat/completions", headers=_headers(), json=body,
                           timeout=timeout or settings().llm_timeout_s)
            if r.status_code >= 500 or r.status_code == 429:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")      # not retried
            data = r.json()
            choice = data["choices"][0]
            msg = choice["message"]
            msg["finish_reason"] = choice.get("finish_reason")
            msg["usage"] = data.get("usage", {})
            return msg
        except (httpx.HTTPError, LLMError, KeyError, ValueError) as e:
            last = e
            if isinstance(e, LLMError) and str(e).startswith("HTTP 4") and "429" not in str(e)[:9]:
                break
            time.sleep(2 * (attempt + 1))
    raise LLMError(f"model call failed: {last}")


def _parse(msg: dict) -> dict:
    text = (msg.get("content") or "").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if msg.get("finish_reason") == "length":
            raise LLMError("the model's answer was cut off (max_tokens)") from e
        raise LLMError(f"the model returned invalid JSON: {text[:200]}") from e


def chat_json(messages: list[dict], schema: dict, **kw) -> dict:
    """A JSON object matching `schema`.

    Uses JSON mode with the schema written into the prompt, then validates. (Strict schema decoding on this vLLM
    lets the model pad its answer with whitespace until max_tokens, so it isn't used.) One retry shows the model its
    validation errors.
    """
    import jsonschema
    msgs = [dict(m) for m in messages]
    msgs[0]["content"] += ("\n\nAnswer with ONE JSON object that matches this JSON Schema exactly (every key required, "
                           "enum values spelled exactly):\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for attempt in range(2):
        msg = chat(msgs, json_mode=True, **kw)
        data = _parse(msg)
        errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message[:160]}" for e in validator.iter_errors(data)]
        if not errors:
            return data
        msgs = msgs + [{"role": "assistant", "content": msg.get("content") or ""},
                       {"role": "user", "content": "Your JSON doesn't match the schema:\n- " + "\n- ".join(errors[:12]) +
                                                   "\nReturn the corrected, complete JSON object only."}]
    raise LLMError("the model's JSON didn't match the schema: " + "; ".join(errors[:5]))


def embed(texts: list[str], batch: int = 32) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        part = [t[:4000] or " " for t in texts[i:i + batch]]
        for attempt in range(3):
            try:
                r = httpx.post(f"{settings().llm_api_url}/embeddings", headers=_headers(),
                               json={"model": settings().embedding_model, "input": part}, timeout=120)
                r.raise_for_status()
                out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d.get("index", 0))]
                break
            except (httpx.HTTPError, KeyError) as e:
                if attempt == 2:
                    raise LLMError(f"embedding failed: {e}") from e
                time.sleep(2 * (attempt + 1))
    return out


def available() -> bool:
    key = settings().llm_api_key
    return bool(key) and key.isascii() and " " not in key
