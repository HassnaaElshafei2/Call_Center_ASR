"""EgypTalk-ASR-v2 (NAMAA, NVIDIA NeMo FastConformer hybrid RNNT/CTC)."""
import glob
import os
import tarfile
import tempfile

from _common import device, serve

_model = None


def _load():
    global _model
    if _model is None:
        import torch
        from huggingface_hub import snapshot_download
        from nemo.collections.asr.models import ASRModel
        # from_pretrained fails on this repo (no model_config.yaml), so restore the .nemo file directly
        repo = snapshot_download("NAMAA-Space/EgypTalk-ASR-v2")
        nemo = glob.glob(repo + "/**/*.nemo", recursive=True)
        if nemo:
            path = nemo[0]
        else:
            cfg = glob.glob(repo + "/**/*config*.yaml", recursive=True)
            ckpt = glob.glob(repo + "/**/*.ckpt", recursive=True)
            if not (cfg and ckpt):
                raise RuntimeError("no .nemo file and no config+ckpt pair in the repo")
            path = os.path.join(tempfile.gettempdir(), "egyptalk_packed.nemo")
            with tarfile.open(path, "w") as tar:
                tar.add(cfg[0], arcname="model_config.yaml")
                tar.add(ckpt[0], arcname="model_weights.ckpt")
        dev = device()
        _model = ASRModel.restore_from(path, map_location="cuda" if dev == "cuda" else "cpu")
        _model.eval()
    return _model


def _make(decoder):
    def load():
        m = _load()

        def run(paths, opts):
            import torch
            m.change_decoding_strategy(decoder_type=decoder)   # raises if unsupported: no silent fallback
            with torch.inference_mode():
                hyps = m.transcribe(paths, batch_size=16)
            if isinstance(hyps, tuple):
                hyps = hyps[0]
            texts = []
            for h in hyps:
                if isinstance(h, list):
                    h = h[0] if h else ""
                texts.append(h if isinstance(h, str) else getattr(h, "text", str(h)))
            return texts
        return run
    return load


serve({"egyptalk-rnnt": _make("rnnt"), "egyptalk-ctc": _make("ctc")}, shared_cache=True)
