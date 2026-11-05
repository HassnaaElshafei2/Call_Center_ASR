"""Shared loop for every model worker. Runs inside that model's own venv.

Protocol (one JSON object per line):
  stdin : {"id": 1, "model": "<key>", "paths": [...], "opts": {...}}
  stdout: {"id": 1, "texts": [...], "seconds": 1.2}   or   {"id": 1, "error": "..."}
Anything libraries print goes to stderr (the worker log), so stdout stays clean.
"""
import gc
import json
import os
import sys
import time
import traceback


def device():
    """cuda (NVIDIA, incl. DGX Spark) > mps (Apple Silicon) > cpu. Override with ASR_DEVICE."""
    forced = os.environ.get("ASR_DEVICE")
    if forced:
        return forced
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def half_dtype():
    """bf16 where supported, fp16 on older GPUs (T4), fp32 on CPU."""
    import torch
    d = device()
    if d == "cuda":
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    if d == "mps":
        return torch.float16
    return torch.float32


def free_memory():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def serve(loaders, shared_cache=False):
    """loaders: {model_key: () -> callable(paths, opts) -> list[str]}"""
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    cache = {}

    def reply(obj):
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out.flush()

    reply({"ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        try:
            key = req["model"]
            if key not in loaders:
                raise ValueError(f"unknown model '{key}' for this worker")
            if key not in cache:
                if cache and not shared_cache:          # keep one model in memory per worker
                    cache.clear()
                    free_memory()
                print(f"loading {key} on {device()} ...", file=sys.stderr, flush=True)
                cache[key] = loaders[key]()
            t0 = time.time()
            texts = cache[key](req["paths"], req.get("opts") or {})
            reply({"id": req.get("id"), "texts": [t if isinstance(t, str) else str(t or "") for t in texts],
                   "seconds": time.time() - t0})
        except BaseException as e:                       # noqa: BLE001 - report everything to the app
            traceback.print_exc()
            reply({"id": req.get("id"), "error": f"{type(e).__name__}: {e}"})
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                break
