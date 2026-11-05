"""transformers models: Whisper large-v3 (stock / Egyptian LoRA, with or without a domain prompt)
and Cohere Transcribe Arabic (local)."""
import os
import re

import numpy as np
import soundfile as sf

from _common import device, half_dtype, serve

SR = 16000
EGY_ADAPTER = "AbdelrahmanHassan/whisper-large-v3-egyptian-arabic"
COHERE_AR = "CohereLabs/cohere-transcribe-arabic-07-2026"


def _audio(path):
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(1)
    if sr != SR:
        import librosa
        a = librosa.resample(a, orig_sr=sr, target_sr=SR)
    return a


def _norm(t):
    t = re.sub(r"[ً-ْٰـ]", "", t)
    t = re.sub("[إأآا]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def _whisper(egyptian: bool):
    def load():
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor, pipeline
        dtype = half_dtype()
        base = WhisperForConditionalGeneration.from_pretrained("openai/whisper-large-v3", torch_dtype=dtype)
        if egyptian:
            from peft import PeftModel        # needs torchao uninstalled (it breaks peft)
            model = PeftModel.from_pretrained(base, EGY_ADAPTER).merge_and_unload()
        else:
            model = base
        proc = WhisperProcessor.from_pretrained("openai/whisper-large-v3")
        asr = pipeline("automatic-speech-recognition", model=model, tokenizer=proc.tokenizer,
                       feature_extractor=proc.feature_extractor, torch_dtype=dtype, device=device())

        def run(paths, opts):
            gen = {"language": opts.get("language", "ar"), "task": "transcribe", "num_beams": 1}
            prompt = opts.get("prompt", "")
            if prompt:
                gen["prompt_ids"] = proc.get_prompt_ids(prompt, return_tensors="pt").to(asr.model.device)
            inputs = [{"raw": _audio(p), "sampling_rate": SR} for p in paths]
            try:
                outs = asr(inputs, batch_size=8, generate_kwargs=gen)
            except Exception:                 # batched prompts fail on some versions
                outs = [asr(x, generate_kwargs=gen) for x in inputs]
            texts = [o["text"].strip() for o in outs]
            if prompt:
                pn = _norm(prompt)
                pw = set(pn.split())
                clean = []
                for t in texts:
                    n = _norm(t)
                    if n.startswith(pn):                       # prompt echoed back in front
                        t = n[len(pn):].strip()
                    w = _norm(t).split()
                    if len(w) >= 4 and sum(x in pw for x in w) / len(w) > 0.6:
                        t = ""                                   # pure prompt echo on unclear audio
                    clean.append(t)
                texts = clean
            return texts
        return run
    return load


def _cohere_arabic():
    from huggingface_hub import login
    from transformers import AutoProcessor, CohereAsrForConditionalGeneration
    if os.environ.get("HF_TOKEN"):
        login(token=os.environ["HF_TOKEN"])              # gated model: accept its terms on HF first
    proc = AutoProcessor.from_pretrained(COHERE_AR)
    model = CohereAsrForConditionalGeneration.from_pretrained(
        COHERE_AR, device_map="auto" if device() == "cuda" else None)
    if device() != "cuda":
        model = model.to(device())

    def run(paths, opts):
        lang = opts.get("language", "ar")
        texts = []
        for p in paths:                                   # segments are <= 15 s, no chunking needed
            inputs = proc(_audio(p), sampling_rate=SR, return_tensors="pt", language=lang)
            inputs.to(model.device, dtype=model.dtype)
            out = model.generate(**inputs, max_new_tokens=384)
            t = proc.decode(out, skip_special_tokens=True)
            texts.append(t if isinstance(t, str) else " ".join(t))
        return texts
    return run


serve({
    "whisper": _whisper(False),
    "whisper-prompt": _whisper(False),
    "whisper-egy": _whisper(True),
    "whisper-egy-prompt": _whisper(True),
    "cohere-arabic": _cohere_arabic,
})
