"""Audio loading and the optional preprocessing chain.

Steps (each can be switched on/off in the UI; "Apply preprocessing" ticks every step that can run):
  declip     restores clipped peaks (ffmpeg adeclip)
  filter     80 Hz high-pass + dynaudnorm loudness normalisation (ffmpeg)
  dereverb   weighted prediction error dereverberation, for speakerphone echo (nara-wpe)
  denoise    non-stationary spectral gating (noisereduce, prop_decrease=0.8)
  enhance    neural speech enhancement (ClearVoice FRCRN_SE_16K, slow, own venv)
  superres   speech super-resolution to 48 kHz (ClearVoice MossFormer2_SR_48K, slow, own venv)
  loudness   EBU R128 loudness to -23 LUFS with a -1 dBFS peak cap (pyloudnorm)
Diarization always runs on the original audio; only the ASR models get the processed audio.
Enhancement can lower recognition accuracy on modern models, so compare runs with and without each step.
"""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .workers import POOL

SR = 16000
STEPS = {
    "declip": "Repair clipped audio (ffmpeg)",
    "filter": "High-pass + loudness normalisation (ffmpeg)",
    "dereverb": "Reduce echo (WPE dereverberation)",
    "denoise": "Noise reduction (noisereduce)",
    "enhance": "Neural speech enhancement (ClearVoice, slow)",
    "superres": "Super-resolution to 48 kHz (ClearVoice, slow)",
    "loudness": "Loudness to -23 LUFS (pyloudnorm)",
}
ORDER = list(STEPS)                      # the order the steps run in
NEEDS_ENHANCE_ENV = ("enhance", "superres")


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


def dereverb(a, size=512, shift=128, taps=10, delay=3, iterations=3):
    from nara_wpe.utils import istft, stft
    from nara_wpe.wpe import wpe
    spec = stft(a[None], size=size, shift=shift).transpose(2, 0, 1)      # (freq, channel, time)
    clean = wpe(spec, taps=taps, delay=delay, iterations=iterations, statistics_mode="full")
    y = istft(clean.transpose(1, 2, 0), size=size, shift=shift)[0]
    return np.pad(y, (0, max(0, len(a) - len(y))))[: len(a)].astype(np.float32)


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
        if step == "declip":
            ffmpeg_to_16k(cur, out, af="adeclip")
        elif step == "filter":
            ffmpeg_to_16k(cur, out, af="highpass=f=80,dynaudnorm")
        elif step == "dereverb":
            a, sr = read(cur)
            write(out, dereverb(a), sr)
        elif step == "denoise":
            a, sr = read(cur)
            write(out, denoise(a, sr), sr)
        elif step == "enhance":
            POOL.call("enhance", "enhance", [cur], {"out": str(out)})
        elif step == "loudness":
            a, sr = read(cur)
            write(out, loudness(a, sr), sr)
        elif step == "superres":
            hi = workdir / "pre_superres_48k.wav"
            POOL.call("enhance", "superres", [cur], {"out": str(hi)})
            ffmpeg_to_16k(hi, out)          # models take 16 kHz; the restored 4-8 kHz band is kept
        cur = out
    return cur
