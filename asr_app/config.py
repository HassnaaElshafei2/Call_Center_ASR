"""Paths and switches. Everything can be overridden with environment variables."""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
ENVS_DIR = Path(os.environ.get("ASR_ENVS_DIR", APP_DIR / "venvs"))        # one venv per model family
DATA_DIR = Path(os.environ.get("ASR_DATA_DIR", APP_DIR / "data" / "calls"))  # example calls + reference JSON/SRT
WORK_DIR = Path(os.environ.get("ASR_WORK_DIR", APP_DIR / "work"))        # segment WAVs, outputs (per audio)
RESULTS_CSV = Path(os.environ.get("ASR_RESULTS_CSV", APP_DIR / "results" / "runs.csv"))
LOG_DIR = Path(os.environ.get("ASR_LOG_DIR", APP_DIR / "logs"))

# Real customer audio must not leave our infrastructure. Cloud models stay disabled
# unless this is explicitly set (only for synthetic or consented audio).
ALLOW_CLOUD = os.environ.get("ALLOW_CLOUD_MODELS", "0") == "1"

# How many model environments may stay loaded at once (each holds a model in GPU memory).
MAX_WORKERS = int(os.environ.get("ASR_MAX_WORKERS", "2"))

HF_TOKEN = os.environ.get("HF_TOKEN", "")  # needed for pyannote (gated) and Cohere Arabic (gated)

# Model downloads stay next to the app (not in the user profile) unless overridden. Workers inherit these.
# Set before huggingface_hub is imported: it reads them once, at import.
MODEL_CACHE = Path(os.environ.get("ASR_MODEL_CACHE", APP_DIR / "model_cache"))
os.environ.setdefault("HF_HOME", str(MODEL_CACHE / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(MODEL_CACHE / "torch"))
os.environ.setdefault("NEMO_CACHE_DIR", str(MODEL_CACHE / "nemo"))

AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".amr", ".opus")
REF_EXTS = (".json", ".srt", ".txt")

for d in (WORK_DIR, LOG_DIR, RESULTS_CSV.parent):
    d.mkdir(parents=True, exist_ok=True)
