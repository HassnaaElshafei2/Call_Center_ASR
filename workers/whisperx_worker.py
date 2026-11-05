"""WhisperX large-v3 (faster-whisper backend). Kept in its own venv: it pins its own torch."""
from _common import device, serve


def load():
    import whisperx
    dev = "cuda" if device() == "cuda" else "cpu"         # ctranslate2 has no MPS backend
    model = whisperx.load_model("large-v3", dev, compute_type="float16" if dev == "cuda" else "int8")

    def run(paths, opts):
        lang = opts.get("language", "ar")
        texts = []
        for p in paths:
            result = model.transcribe(whisperx.load_audio(p), batch_size=16, language=lang)
            texts.append(" ".join(s["text"].strip() for s in result["segments"]))
        return texts
    return run


serve({"whisperx": load})
