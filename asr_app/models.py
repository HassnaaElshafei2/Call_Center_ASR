"""Every model Hassnaa and Esraa tried, in one registry.

backend "worker": runs in its own venv (see workers/ and setup_envs.sh).
backend "cloud":  calls an external API; disabled unless ALLOW_CLOUD_MODELS=1.
"""
from dataclasses import dataclass, field

from . import cloud
from .config import ALLOW_CLOUD
from .workers import POOL, env_installed

DEFAULT_PROMPT = ("مكالمة خدمة عملاء باللهجة المصرية. أهلاً بحضرتك يا فندم، القسط، الأقساط، الكارت، "
                  "إنستاباي، فوري، أديب، بي تك، التحصيل، الغرامة، المتأخرات.")


@dataclass
class ModelSpec:
    key: str
    name: str
    tried_by: str
    env: str = ""                 # worker environment
    backend: str = "worker"
    opts: dict = field(default_factory=dict)
    uses_prompt: bool = False
    note: str = ""

    @property
    def cloud(self):
        return self.backend == "cloud"

    def label(self):
        tag = f"  [{self.tried_by}]"
        if self.cloud:
            tag += "  ☁ cloud" + ("" if ALLOW_CLOUD else " (disabled)")
        return self.name + tag


MODELS = [
    # --- Hassnaa ---
    ModelSpec("egyptalk-rnnt", "EgypTalk-ASR-v2 (NeMo, RNNT)", "Hassnaa", "nemo",
              note="Best so far on both calls; fails safely (blank instead of invented text)."),
    ModelSpec("egyptalk-ctc", "EgypTalk-ASR-v2 (NeMo, CTC decoder)", "Hassnaa", "nemo"),
    ModelSpec("audar-turbo", "Audar-ASR-V1 Turbo (Qwen3-ASR)", "Hassnaa", "qwen",
              note="Invents fluent sentences on short agent clips. Limited commercial licence."),
    ModelSpec("omni-1b", "Omnilingual ASR 1B (Meta)", "Hassnaa", "omni", opts={"card": "omniASR_LLM_1B"}),
    ModelSpec("omni-3b", "Omnilingual ASR 3B (Meta)", "Hassnaa", "omni", opts={"card": "omniASR_LLM_3B"},
              note="Needs ~24 GB system RAM to load."),
    ModelSpec("omni-7b", "Omnilingual ASR 7B (Meta)", "Hassnaa", "omni", opts={"card": "omniASR_LLM_7B"},
              note="Needs ~17 GB VRAM; run on the Spark."),
    ModelSpec("whisper-egy-prompt", "Whisper large-v3 Egyptian fine-tune + domain prompt", "Hassnaa", "hf",
              uses_prompt=True, note="Best Whisper setup in v3."),
    ModelSpec("whisper-prompt", "Whisper large-v3 + domain prompt", "Hassnaa", "hf", uses_prompt=True),
    # --- both ---
    ModelSpec("whisper-egy", "Whisper large-v3 Egyptian fine-tune (LoRA)", "Hassnaa + Esraa", "hf"),
    ModelSpec("whisper", "Whisper large-v3", "Hassnaa + Esraa", "hf"),
    # --- Esraa ---
    ModelSpec("whisperx", "WhisperX large-v3", "Esraa", "whisperx"),
    ModelSpec("cohere-arabic", "Cohere Transcribe Arabic (local, HF)", "Esraa", "hf",
              note="Gated on Hugging Face: accept the terms first."),
    ModelSpec("openai-gpt-transcribe", "OpenAI gpt-transcribe (API)", "Esraa", backend="cloud"),
    ModelSpec("cohere-api", "Cohere Transcribe (API)", "Esraa", backend="cloud"),
]
BY_KEY = {m.key: m for m in MODELS}
BY_LABEL = {m.label(): m for m in MODELS}


def status(m: ModelSpec) -> str:
    if m.cloud:
        return "ready" if ALLOW_CLOUD else "disabled (set ALLOW_CLOUD_MODELS=1, consented audio only)"
    return "ready" if env_installed(m.env) else f"not installed (./setup_envs.sh {m.env})"


def transcribe(m: ModelSpec, paths, prompt: str = "", language: str = "ar"):
    """Returns (texts, seconds)."""
    opts = dict(m.opts, language=language)
    if m.uses_prompt:
        opts["prompt"] = prompt or DEFAULT_PROMPT
    if m.cloud:
        if not ALLOW_CLOUD:
            raise RuntimeError("Cloud models are disabled: real customer audio must not leave our servers. "
                               "Start the app with ALLOW_CLOUD_MODELS=1 only for synthetic or consented audio.")
        return cloud.transcribe(m.key, paths, language)
    resp = POOL.call(m.env, m.key, paths, opts)
    return resp["texts"], resp.get("seconds", 0.0)
