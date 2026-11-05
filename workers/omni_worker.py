"""Meta Omnilingual ASR (1B / 3B / 7B LLM cards). Tries Egyptian Arabic, then MSA."""
import sys

from _common import serve


def _make(card):
    def load():
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        p = ASRInferencePipeline(model_card=card)

        def run(paths, opts):
            err = None
            for lang in ("arz_Arab", "arb_Arab"):
                try:
                    texts = []
                    for i in range(0, len(paths), 8):
                        chunk = paths[i:i + 8]
                        texts += [str(t) for t in p.transcribe(chunk, lang=[lang] * len(chunk), batch_size=4)]
                    return texts
                except Exception as e:  # noqa: BLE001
                    err = e
                    print(f"lang {lang} failed: {e}", file=sys.stderr)
            raise RuntimeError(f"all language codes failed: {err}")
        return run
    return load


serve({"omni-1b": _make("omniASR_LLM_1B"), "omni-3b": _make("omniASR_LLM_3B"), "omni-7b": _make("omniASR_LLM_7B")})
