"""Cloud models (direct APIs and OpenRouter). Keys come from environment variables only (never hard-code them)."""
import base64
import os
import time
from functools import partial

OPENROUTER_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_ATTEMPTS = 3         # one failed segment should not lose a whole paid run
CHAT_INSTRUCTION = ("Transcribe this Egyptian Arabic phone call audio word for word, in Arabic script. "
                    "Do not translate, summarise or correct it. Output only the transcript. "
                    "If there is no speech, output nothing.")

# app key -> OpenRouter model id, endpoint type, whether to require Zero Data Retention routing.
# zdr=True only where OpenRouter lists a ZDR endpoint (https://openrouter.ai/api/v1/endpoints/zdr).
OPENROUTER_MODELS = {
    "or-scribe-v2": ("elevenlabs/scribe-v2", "stt", True),
    "or-gpt-4o-transcribe": ("openai/gpt-4o-transcribe", "stt", False),
    "or-gpt-transcribe": ("openai/gpt-transcribe", "stt", False),
    "or-gemini-3.8-flash": ("google/gemini-3.8-flash", "chat", True),
    "or-gemini-4-argon": ("google/gemini-4-argon", "chat", True),
}


def _openai(path, language):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with open(path, "rb") as f:
        try:
            r = client.audio.transcriptions.create(model="gpt-transcribe", file=f, language=language)
        except Exception:
            f.seek(0)                                   # retry without the language hint
            r = client.audio.transcriptions.create(model="gpt-transcribe", file=f)
    return r.text


def _cohere(path, language):
    import cohere
    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    with open(path, "rb") as f:
        r = co.audio.transcriptions.create(model="cohere-transcribe-03-2026", language=language, file=f)
    return getattr(r, "text", str(r))


def _openrouter_post(endpoint, body):
    import httpx
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    for attempt in range(1, OPENROUTER_ATTEMPTS + 1):
        try:
            r = httpx.post(f"{OPENROUTER_URL}/{endpoint}", headers=headers, json=body, timeout=120)
        except httpx.TransportError as e:
            if attempt == OPENROUTER_ATTEMPTS:
                raise RuntimeError(f"OpenRouter request failed for {body['model']}: {e}") from e
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code != 429 and r.status_code < 500 or attempt == OPENROUTER_ATTEMPTS:
                raise RuntimeError(f"OpenRouter returned HTTP {r.status_code} for {body['model']}: {r.text[:300]}")
        time.sleep(2 ** attempt)


def _openrouter(key, path, language):
    model, kind, zdr = OPENROUTER_MODELS[key]
    with open(path, "rb") as f:
        audio = {"data": base64.b64encode(f.read()).decode("ascii"), "format": "wav"}
    body = {"model": model}
    if zdr:
        body["provider"] = {"zdr": True}
    if kind == "stt":
        return _openrouter_post("audio/transcriptions", {**body, "input_audio": audio, "language": language})["text"]
    messages = [{"role": "user", "content": [{"type": "text", "text": CHAT_INSTRUCTION},
                                             {"type": "input_audio", "input_audio": audio}]}]
    r = _openrouter_post("chat/completions", {**body, "messages": messages, "temperature": 0})
    return r["choices"][0]["message"].get("content") or ""


_FN = {"openai-gpt-transcribe": (_openai, "OPENAI_API_KEY"), "cohere-api": (_cohere, "COHERE_API_KEY"),
       **{k: (partial(_openrouter, k), "OPENROUTER_API_KEY") for k in OPENROUTER_MODELS}}


def missing_key(key):
    """Name of the environment variable this model still needs, or None."""
    env_key = _FN[key][1]
    return None if os.environ.get(env_key) else env_key


def transcribe(key, paths, language="ar"):
    fn, env_key = _FN[key]
    if not os.environ.get(env_key):
        raise RuntimeError(f"Missing environment variable {env_key}")
    t0 = time.time()
    texts = [fn(p, language) for p in paths]
    return texts, time.time() - t0
