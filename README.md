# Egyptian Arabic call ASR: model comparison app

One web app for every model Hassnaa and Esraa tried. Pick a call, a model, and whether to preprocess the audio. The app shows the **reference conversation on the left**, the **model's conversation on the right**, and the **score** (WER/CER overall, per agent/customer, and key-term recall).

Runs on any machine:

| Machine | Works? | Notes |
|---|---|---|
| NVIDIA GPU (DGX Spark, workstation, cloud VM) | yes, fastest | all models |
| Apple Silicon Mac | yes | uses MPS; WhisperX runs on CPU |
| CPU only | yes, slow | fine for EgypTalk; Whisper/Audar/Omnilingual take minutes per call; 7B models are impractical |
| Google Colab | technically | **synthetic or consented audio only** (Colab is Google's servers) |

## Install

Needs Python 3.10–3.12, `ffmpeg`, and a Hugging Face **Read** token with the terms accepted on
`pyannote/speaker-diarization-community-1` (and `CohereLabs/cohere-transcribe-arabic-07-2026` if you use it).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./setup_envs.sh            # every model environment (or e.g. ./setup_envs.sh nemo hf)
```

`setup_envs.sh` creates one environment per model family under `venvs/`, because the models need
conflicting libraries:

| Environment | Models |
|---|---|
| `nemo` | EgypTalk-ASR-v2 (RNNT, CTC) |
| `hf` | Whisper large-v3 and the Egyptian fine-tune (with or without the domain prompt), Cohere Transcribe Arabic (local) |
| `qwen` | Audar-ASR Turbo |
| `omni` | Omnilingual ASR 1B / 3B / 7B |
| `whisperx` | WhisperX large-v3 |
| `enhance` | ClearVoice super-resolution (preprocessing step) |

To pick the torch build, set `TORCH_INDEX`:
- CPU-only machine: `TORCH_INDEX=https://download.pytorch.org/whl/cpu ./setup_envs.sh`
- DGX Spark (ARM + CUDA): `TORCH_INDEX=https://download.pytorch.org/whl/cu130 ./setup_envs.sh`

If one environment fails to install, the other models still work. The **Models and install status**
panel in the app shows which are ready.

## Run

```bash
export HF_TOKEN=hf_...          # never paste tokens into notebooks or code
python app.py                   # http://127.0.0.1:7860
```

To share the app with the team on the office network: `ASR_HOST=0.0.0.0 python app.py`.
Public links (`share=True`) are switched off on purpose: they expose real customer calls.

## Using it
1. **Example call**: choose one of the calls in `data/calls/`. Its reference JSON is matched by the
   recording id in the file name. Or upload any audio, with an optional JSON/SRT reference.
2. **Model**: ☁ cloud models (OpenRouter, OpenAI, Cohere API) are disabled
   unless the app is started with `ALLOW_CLOUD_MODELS=1` plus the matching key (`OPENROUTER_API_KEY`,
   `OPENAI_API_KEY`, `COHERE_API_KEY`), and only for synthetic or consented audio. Models without their
   key show as "needs ..." in the status panel and are skipped by **Run all installed models**.
3. **Apply preprocessing**: ticks every available step (high-pass + dynaudnorm, noise reduction,
   super-resolution if its environment is installed, -23 LUFS loudness), and you can then untick any
   you don't want. Only the ASR models hear the processed audio; diarization always uses the original.
4. **Transcribe**. Every run is added to the table and to `results/runs.csv`, and its JSON + SRT can
   be downloaded. **Run all installed models** fills the table for one call in one click.

Preprocessing and diarization are cached per call, so switching models on the same call skips straight
to transcription.

## How it works
`audio → 16 kHz mono → [preprocessing] → Silero VAD + pyannote (exclusive turns, 2 or 2–3 voices) →
segments ≤ 15 s cut at pauses → model → loop/hallucination clean-up → agent/customer mapping → score`

- Agent/customer mapping: the speaker who uses the most service phrases («حضرتك», «فندم», «معاك», …)
  is the agent. **Swap agent / customer** fixes it when that guess is wrong.
- Scores ignore IVR lines unless **Score the IVR lines too** is ticked.
- The references look model-generated (probably Gemini), so scores measure agreement with them, and
  differences under ~0.02 WER are noise.

## Adding a model
1. Add a `ModelSpec` to `asr_app/models.py`.
2. Add a loader for its key in the matching `workers/<env>_worker.py` (or a new worker + a case in `setup_envs.sh`).
   A loader returns a function `run(paths, opts) -> list[str]` (one text per segment WAV).

## Files
```
app.py                 Gradio UI
asr_app/               pipeline: preprocess, segment, models registry, worker pool, scoring, rendering
workers/               one script per model environment (JSON lines over stdin/stdout)
setup_envs.sh          creates the model environments
data/calls/            example calls + reference JSON (real customer data: not committed, see .gitignore)
results/runs.csv       every run's scores
logs/worker_*.log      model logs (look here when a model fails)
```
