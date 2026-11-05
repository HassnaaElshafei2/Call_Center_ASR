"""Esraa's speech super-resolution (ClearVoice MossFormer2_SR_48K).
Own venv because clearvoice pins numpy 1.26, which breaks pyannote in the main app.
Request: {"model": "superres", "paths": [in_16k.wav], "opts": {"out": out_48k.wav}} -> texts = [out path]"""
import numpy as np
import soundfile as sf

from _common import serve


def load():
    from clearvoice import ClearVoice
    sr_model = ClearVoice(task="speech_super_resolution", model_names=["MossFormer2_SR_48K"])

    def run(paths, opts):
        res = sr_model(input_path=paths[0], online_write=False)
        if isinstance(res, dict):
            res = next(iter(res.values()))
        res = res.cpu().numpy() if hasattr(res, "cpu") else np.asarray(res)
        sf.write(opts["out"], np.atleast_2d(res)[0].astype(np.float32), 48000)
        return [opts["out"]]
    return run


serve({"superres": load})
