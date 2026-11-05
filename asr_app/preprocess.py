"""Audio loading and the optional preprocessing chain.

Steps (each can be switched on/off in the UI; the "Preprocessing" checkbox enables the selected ones):
  filter     Hassnaa: 80 Hz high-pass + dynaudnorm loudness normalisation (ffmpeg)
  denoise    Esraa:   non-stationary spectral gating (noisereduce, prop_decrease=0.8)
  superres   Esraa:   speech super-resolution to 48 kHz (ClearVoice MossFormer2_SR_48K, slow, own venv)
  loudness   Esraa:   EBU R128 loudness to -23 LUFS with a -1 dBFS peak cap (pyloudnorm)
Diarization always runs on the original audio; only the ASR models get the processed audio.
"""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .workers import POOL

SR = 16000
STEPS = {
    "filter": "High-pass + loudness normalisation (ffmpeg) [Hassnaa]",
    "denoise": "Noise reduction (noisereduce) [Esraa]",
    "superres": "Super-resolution to 48 kHz (ClearVoice, slow) [Esraa]",
    "loudness": "Loudness to -23 LUFS (pyloudnorm) [Esraa]",
}
DEFAULT_STEPS = ["filter", "denoise", "loudness"]
ORDER = ["filter", "denoise", "superres", "loudness"]


def ffmpeg_to_16k(src, dst, af=None):
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if af:
        cmd += ["-af", af]
    cmd += ["-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {Path(src).name}: {r.stderr[-500:]}")
    return Path(dst)


def read(path):
    a, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return a.mean(1), sr


def write(path, a, sr=SR):
    sf.write(str(path), a.astype(np.float32), sr, subtype="PCM_16")
    return Path(path)


def denoise(a, sr, prop_decrease=0.8):
    import noisereduce as nr
    return nr.reduce_noise(y=a, sr=sr, stationary=False, prop_decrease=prop_decrease).astype(np.float32)


def loudness(a, sr, target_lufs=-23.0, peak_db=-1.0):
    import pyloudnorm as pyln
    if np.max(np.abs(a)) < 1e-4:
        return a
    loud = pyln.Meter(sr).integrated_loudness(a)
    if not np.isfinite(loud):
        return a
    y = pyln.normalize.loudness(a, loud, target_lufs)
    limit = 10 ** (peak_db / 20)
    m = np.max(np.abs(y))
    return (y * (limit / m) if m > limit else y).astype(np.float32)


def run_chain(original_16k: Path, steps, workdir: Path, log=print) -> Path:
    """Returns the path of the 16 kHz mono WAV the ASR models should read."""
    cur = Path(original_16k)
    for step in [s for s in ORDER if s in steps]:
        out = workdir / f"pre_{step}.wav"
        log(f"preprocessing: {step}")
        if step == "filter":
            ffmpeg_to_16k(cur, out, af="highpass=f=80,dynaudnorm")
        elif step == "denoise":
            a, sr = read(cur)
            write(out, denoise(a, sr), sr)
        elif step == "loudness":
            a, sr = read(cur)
            write(out, loudness(a, sr), sr)
        elif step == "superres":
            hi = workdir / "pre_superres_48k.wav"
            POOL.call("enhance", "superres", [cur], {"out": str(hi)})
            ffmpeg_to_16k(hi, out)          # models take 16 kHz; the restored 4-8 kHz band is kept
        cur = out
    return cur
