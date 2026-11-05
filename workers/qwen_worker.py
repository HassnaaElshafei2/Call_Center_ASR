"""Audar-ASR-V1 Turbo via the qwen-asr package."""
import re

from _common import device, half_dtype, serve


def load():
    from qwen_asr import Qwen3ASRModel
    dev = device()
    m = Qwen3ASRModel.from_pretrained("audarai/Audar-ASR-V1-Turbo", dtype=half_dtype(),
                                      device_map="cuda:0" if dev == "cuda" else dev, max_new_tokens=256)

    def run(paths, opts):
        texts = []
        for i in range(0, len(paths), 8):
            chunk = paths[i:i + 8]
            for r in m.transcribe(audio=chunk, language=["Arabic"] * len(chunk)):
                t = r if isinstance(r, str) else getattr(r, "text", None) or (
                    r.get("text") if isinstance(r, dict) else str(r))
                texts.append(re.sub(r"^\s*language\s+\S+\s*<asr_text>", "", t or "").strip())
        return texts
    return run


serve({"audar-turbo": load})
