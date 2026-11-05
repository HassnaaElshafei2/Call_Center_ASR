"""Egyptian Arabic call ASR: compare every model we tried (Hassnaa + Esraa) on any call.

    python app.py            ->  http://127.0.0.1:7860
Environment: HF_TOKEN (pyannote, gated models), ASR_HOST/ASR_PORT, ALLOW_CLOUD_MODELS=1 (consented audio only).
"""
import os
import time
import traceback
from pathlib import Path

import gradio as gr

from asr_app import ground_truth, models, pipeline, render, scoring
from asr_app.config import ALLOW_CLOUD, AUDIO_EXTS, DATA_DIR
from asr_app.preprocess import DEFAULT_STEPS, STEPS

HIST_COLS = ["time", "audio", "model", "preprocessing", "diarization", "wer", "cer",
             "agent_wer", "customer_wer", "asr_seconds"]


# ---------------- helpers ----------------
def example_calls():
    if not DATA_DIR.exists():
        return []
    return [(p.name, str(p)) for p in sorted(DATA_DIR.rglob("*")) if p.suffix.lower() in AUDIO_EXTS]


def model_choices():
    return [(m.label(), m.key) for m in models.MODELS]


def models_table():
    return [[m.name, m.tried_by, "cloud API" if m.cloud else m.env, models.status(m), m.note]
            for m in models.MODELS]


def resolve_reference(audio_path, ref_file):
    if ref_file:
        return Path(getattr(ref_file, "name", ref_file))
    if audio_path:
        return ground_truth.find_reference(audio_path, [DATA_DIR, Path(audio_path).parent])
    return None


def show_reference(audio_path, ref_file):
    ref = resolve_reference(audio_path, ref_file)
    if not ref:
        return render.reference_html([]), "No reference found for this audio (upload a JSON/SRT to score it)."
    try:
        items, meta = ground_truth.load_reference(ref)
        return render.reference_html(items, meta), f"Reference: `{ref.name}` ({len(items)} turns)"
    except Exception as e:  # noqa: BLE001
        return render.empty(f"Could not read {ref.name}: {e}"), f"Reference error: {e}"


def pick_example(path):
    if not path:
        return None, None
    ref = ground_truth.find_reference(path)
    return path, (str(ref) if ref else None)


def history_rows(hist):
    return [[h.get(c) for c in HIST_COLS] for h in hist]


# ---------------- main action ----------------
def run_one(audio_path, ref_file, model_key, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
            show_blank, hist, progress, log_lines):
    spec = models.BY_KEY[model_key]

    def log(msg):
        log_lines.append(msg)

    progress(0.05, desc="Preparing audio")
    min_s, max_s = (2, 3) if speakers == "2 or 3 (IVR as a 3rd voice)" else (2, 2)
    prep = pipeline.prepare(audio_path, steps if use_pre else (), use_diar, min_s, max_s, log)
    progress(0.4, desc=f"Transcribing {len(prep.segments)} segments with {spec.name}")
    t0 = time.time()
    rows, secs = pipeline.transcribe(prep, spec, prompt=prompt, swap_roles=swap)
    log(f"{spec.name}: {len(rows)} segments in {time.time() - t0:.0f}s")
    progress(0.9, desc="Scoring")

    ref = resolve_reference(audio_path, ref_file)
    res, score_md, ref_html = None, "No reference transcript, so no score. Upload one to compare.", render.reference_html([])
    if ref:
        items, meta = ground_truth.load_reference(ref)
        ref_html = render.reference_html(items, meta)
        res = scoring.score(items, rows, include_ivr=include_ivr)
        score_md = scoring.to_markdown(res, spec.name)
    audio_name = Path(audio_path).name
    files = pipeline.save_outputs(prep, spec, rows, res, audio_name)
    rec = pipeline.make_record(audio_name, spec, prep, use_diar, res, secs)
    pipeline.log_run(rec)
    hist = hist + [rec]
    return ref_html, render.model_html(rows, show_blank), score_md, files, hist


def run(audio_path, ref_file, model_key, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
        show_blank, hist, progress=gr.Progress()):
    log_lines = []
    if not audio_path:
        return "Upload an audio file or pick an example call first.", gr.update(), gr.update(), gr.update(), \
            gr.update(), hist, history_rows(hist)
    if not model_key:
        return "Pick a model.", gr.update(), gr.update(), gr.update(), gr.update(), hist, history_rows(hist)
    try:
        ref_html, model_html, score_md, files, hist = run_one(
            audio_path, ref_file, model_key, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
            show_blank, hist, progress, log_lines)
        status = "✅ Done.  " + " · ".join(log_lines[-4:])
        return status, ref_html, model_html, score_md, files, hist, history_rows(hist)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        msg = f"❌ {type(e).__name__}: {e}"
        return msg, gr.update(), render.empty(str(e)[:400]), gr.update(), gr.update(), hist, history_rows(hist)


def run_all(audio_path, ref_file, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr, show_blank,
            hist, progress=gr.Progress()):
    """Run every model that is installed (cloud ones only if allowed) on this audio; fill the table."""
    if not audio_path:
        return "Upload an audio file or pick an example call first.", hist, history_rows(hist)
    ready = [m for m in models.MODELS if models.status(m) == "ready"]
    if not ready:
        return "No model environment is installed yet (see README: ./setup_envs.sh).", hist, history_rows(hist)
    errors = []
    for k, m in enumerate(ready):
        progress(k / len(ready), desc=m.name)
        try:
            *_, hist = run_one(audio_path, ref_file, m.key, use_pre, steps, use_diar, speakers, prompt, swap,
                               include_ivr, show_blank, hist, lambda *a, **kw: None, [])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{m.name}: {e}")
    msg = f"Ran {len(ready) - len(errors)}/{len(ready)} models." + (" Errors: " + " | ".join(errors) if errors else "")
    return msg, hist, history_rows(hist)


# ---------------- UI ----------------
CSS = """
.panel-title{font-weight:600;margin:4px 0}
footer{display:none !important}
"""

with gr.Blocks(title="Egyptian ASR comparison") as demo:
    gr.Markdown("## Egyptian Arabic call transcription: model comparison\n"
                "Pick a call, a model and whether to preprocess the audio, then **Transcribe**. "
                "The reference (ground truth) is on the left, the model's conversation on the right.")
    hist_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=1):
            example = gr.Dropdown(example_calls(), value=None, label="Example call (from data/calls)",
                                  info="Its reference transcript is matched automatically by the recording id.")
            audio = gr.Audio(type="filepath", label="Or upload a call (WAV/MP3, any sample rate)")
            ref_file = gr.File(label="Reference transcript (optional: JSON or SRT)", file_types=[".json", ".srt", ".txt"])
            ref_status = gr.Markdown("")
        with gr.Column(scale=1):
            model = gr.Dropdown(model_choices(), value="egyptalk-rnnt", label="Model",
                                info="[name] = who tried it. Cloud models are off unless the app is started with "
                                     "ALLOW_CLOUD_MODELS=1 (consented audio only).")
            use_pre = gr.Checkbox(value=False, label="Apply preprocessing",
                                  info="Only the ASR models hear the processed audio; diarization uses the original.")
            steps = gr.CheckboxGroup([(v, k) for k, v in STEPS.items()], value=DEFAULT_STEPS,
                                     label="Preprocessing steps (used when the box above is ticked)")
            with gr.Accordion("Advanced", open=False):
                use_diar = gr.Checkbox(value=True, label="Speaker diarization (pyannote community-1)",
                                       info="Off = VAD-only segments, no agent/customer split.")
                speakers = gr.Radio(["2", "2 or 3 (IVR as a 3rd voice)"], value="2", label="Number of voices")
                swap = gr.Checkbox(value=False, label="Swap agent / customer (if the automatic mapping is wrong)")
                include_ivr = gr.Checkbox(value=False, label="Score the IVR lines too")
                show_blank = gr.Checkbox(value=False, label="Show segments with no text")
                prompt = gr.Textbox(models.DEFAULT_PROMPT, lines=2, label="Domain prompt (Whisper + prompt models only)")
            with gr.Row():
                btn = gr.Button("Transcribe", variant="primary")
                btn_all = gr.Button("Run all installed models")

    status = gr.Markdown("")
    score_md = gr.Markdown("")
    with gr.Row(equal_height=False):
        with gr.Column():
            gr.Markdown("**Ground truth (reference)**", elem_classes="panel-title")
            ref_view = gr.HTML(render.empty("Pick a call to see its reference transcript."))
        with gr.Column():
            gr.Markdown("**Model output**", elem_classes="panel-title")
            model_view = gr.HTML(render.empty("Run a model to see its transcript here."))

    with gr.Accordion("All runs in this session (also appended to results/runs.csv)", open=True):
        hist_table = gr.Dataframe(headers=HIST_COLS, value=[], interactive=False, wrap=True,
                                  column_widths=["9%", "17%", "20%", "14%", "6%", "6%", "6%", "8%", "8%", "6%"])
    files = gr.File(label="Download this run (JSON + SRT)", file_count="multiple")
    with gr.Accordion("Models and install status", open=False):
        gr.Dataframe(headers=["model", "tried by", "environment", "status", "notes"], value=models_table(),
                     interactive=False, wrap=True)
        if not ALLOW_CLOUD:
            gr.Markdown("Cloud models are disabled: real customer audio must not leave our servers.")

    example.change(pick_example, example, [audio, ref_file])
    audio.change(show_reference, [audio, ref_file], [ref_view, ref_status])
    ref_file.change(show_reference, [audio, ref_file], [ref_view, ref_status])
    inputs = [audio, ref_file, model, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr, show_blank,
              hist_state]
    btn.click(run, inputs, [status, ref_view, model_view, score_md, files, hist_state, hist_table])
    btn_all.click(run_all, [audio, ref_file, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
                            show_blank, hist_state], [status, hist_state, hist_table])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name=os.environ.get("ASR_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("ASR_PORT", "7860")),
        share=False,                           # never publish real calls on a public gradio.live link
        allowed_paths=[str(DATA_DIR)],
        css=CSS,
    )
