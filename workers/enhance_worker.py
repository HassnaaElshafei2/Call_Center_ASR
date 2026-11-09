"""ClearVoice preprocessing: speech enhancement (FRCRN_SE_16K) and super-resolution (MossFormer2_SR_48K).
Own venv because clearvoice pins numpy 1.26, which breaks pyannote in the main app.
Request: {"model": "enhance" | "superres", "paths": [in_16k.wav], "opts": {"out": out.wav}} -> texts = [out path]"""
import numpy as np
import soundfile as sf

from _common import serve


def loader(task, model_name, out_sr):
    def load():
        from clearvoice import ClearVoice
        model = ClearVoice(task=task, model_names=[model_name])

        def run(paths, opts):
            res = model(input_path=paths[0], online_write=False)
            if isinstance(res, dict):
                res = next(iter(res.values()))
            res = res.cpu().numpy() if hasattr(res, "cpu") else np.asarray(res)
            sf.write(opts["out"], np.atleast_2d(res)[0].astype(np.float32), out_sr)
            return [opts["out"]]
        return run
    return load


serve({"enhance": loader("speech_enhancement", "FRCRN_SE_16K", 16000),
       "superres": loader("speech_super_resolution", "MossFormer2_SR_48K", 48000)})
