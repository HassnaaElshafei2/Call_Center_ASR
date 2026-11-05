"""Esraa's cloud models. Keys come from environment variables only (never hard-code them)."""
import os
import time


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


_FN = {"openai-gpt-transcribe": (_openai, "OPENAI_API_KEY"), "cohere-api": (_cohere, "COHERE_API_KEY")}


def transcribe(key, paths, language="ar"):
    fn, env_key = _FN[key]
    if not os.environ.get(env_key):
        raise RuntimeError(f"Missing environment variable {env_key}")
    t0 = time.time()
    texts = [fn(p, language) for p in paths]
    return texts, time.time() - t0
