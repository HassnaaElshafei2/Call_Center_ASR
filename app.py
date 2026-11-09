"""Egyptian Arabic call ASR: compare every model we tried on any call.

    python app.py            ->  http://127.0.0.1:7860
Environment: HF_TOKEN (pyannote, gated models), ASR_HOST/ASR_PORT, ALLOW_CLOUD_MODELS=1 (consented audio only).
"""
import json
import os
import time
import traceback
from pathlib import Path

from asr_app.config import ALLOW_CLOUD, AUDIO_EXTS, DATA_DIR  # first: it sets where models are cached

import gradio as gr

from asr_app import ground_truth, models, pipeline, render, scoring
from asr_app.preprocess import NEEDS_ENHANCE_ENV, STEPS
from asr_app.workers import env_installed

HIST_COLS = ["time", "audio", "model", "preprocessing", "diarization", "wer", "cer",
             "agent_wer", "customer_wer", "asr_seconds"]
HIST_HEADERS = ["Time", "Audio", "Model", "Preprocessing", "Diarization", "WER", "CER",
                "Agent WER", "Customer WER", "Seconds"]
HIST_PERCENT = {"wer", "cer", "agent_wer", "customer_wer"}


# ---------------- helpers ----------------
def example_calls():
    if not DATA_DIR.exists():
        return []
    return [(p.name, str(p)) for p in sorted(DATA_DIR.rglob("*")) if p.suffix.lower() in AUDIO_EXTS]


def is_ready(m):
    return models.status(m) == "ready"


def model_label(m):
    if is_ready(m) or (m.cloud and not ALLOW_CLOUD):       # a disabled cloud model already says so
        return m.label()
    return f"{m.label()}  · needs key" if m.cloud else f"{m.label()}  · not installed"


def model_choices():
    return [(model_label(m), m.key) for m in sorted(models.MODELS, key=lambda m: not is_ready(m))]


def default_model():
    return next((m.key for m in models.MODELS if is_ready(m)), models.MODELS[0].key)


def models_table():
    return [[m.name, "cloud API" if m.cloud else m.env, models.status(m).split(" (")[0], m.note]
            for m in models.MODELS]


def runnable_steps():
    """Steps ticked by Apply preprocessing: all of them, unless the ClearVoice environment is missing."""
    return [k for k in STEPS if k not in NEEDS_ENHANCE_ENV or env_installed("enhance")]


def resolve_reference(audio_path, ref_file):
    if ref_file:
        return Path(getattr(ref_file, "name", ref_file))
    if audio_path:
        return ground_truth.find_reference(audio_path, [DATA_DIR, Path(audio_path).parent])
    return None


def show_reference(audio_path, ref_file):
    ref = resolve_reference(audio_path, ref_file)
    if not ref:
        return render.reference_html([]), "No reference found for this audio."
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
    def cell(h, col):
        v = h.get(col)
        if col in HIST_PERCENT:
            return "–" if v is None else f"{v:.1%}"
        return v
    return [[cell(h, c) for c in HIST_COLS] for h in hist]


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
    res, ref_html = None, render.reference_html([])
    if ref:
        items, meta = ground_truth.load_reference(ref)
        ref_html = render.reference_html(items, meta)
        res = scoring.score(items, rows, include_ivr=include_ivr)
    audio_name = Path(audio_path).name
    files = pipeline.save_outputs(prep, spec, rows, res, audio_name)
    rec = pipeline.make_record(audio_name, spec, prep, use_diar, res, secs)
    pipeline.log_run(rec)
    hist = hist + [rec]
    return ref_html, render.model_html(rows, show_blank), render.score_html(res, spec.name), files, hist


def run(audio_path, ref_file, model_key, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
        show_blank, hist, progress=gr.Progress()):
    log_lines = []
    if not audio_path:
        return render.status_html("info", "Upload an audio file or pick an example call first."), gr.update(), \
            gr.update(), gr.update(), gr.update(), hist, history_rows(hist)
    if not model_key:
        return render.status_html("info", "Pick a model."), gr.update(), gr.update(), gr.update(), gr.update(), \
            hist, history_rows(hist)
    try:
        ref_html, model_html, score, files, hist = run_one(
            audio_path, ref_file, model_key, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
            show_blank, hist, progress, log_lines)
        status = render.status_html("ok", " · ".join(log_lines[-4:]))
        return status, ref_html, model_html, score, gr.update(value=files, visible=True), hist, history_rows(hist)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        status = render.status_html("error", f"{type(e).__name__}: {e}")
        return status, gr.update(), render.empty("This run failed, so there is no transcript."), gr.update(), \
            gr.update(), hist, history_rows(hist)


def run_all(audio_path, ref_file, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr, show_blank,
            hist, progress=gr.Progress()):
    """Run every model that is ready (cloud ones only if allowed) on this audio; fill the table."""
    if not audio_path:
        return render.status_html("info", "Upload an audio file or pick an example call first."), hist, \
            history_rows(hist), gr.update()
    ready = [m for m in models.MODELS if is_ready(m)]
    if not ready:
        return render.status_html("info", "No model is ready yet. See the Models tab."), hist, history_rows(hist), \
            gr.update()
    errors = []
    for k, m in enumerate(ready):
        progress(k / len(ready), desc=m.name)
        try:
            *_, hist = run_one(audio_path, ref_file, m.key, use_pre, steps, use_diar, speakers, prompt, swap,
                               include_ivr, show_blank, hist, lambda *a, **kw: None, [])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{m.name}: {e}")
    msg = f"Ran {len(ready) - len(errors)} of {len(ready)} models." + (" Errors: " + " | ".join(errors) if errors else "")
    return render.status_html("error" if errors else "ok", msg), hist, history_rows(hist), gr.Tabs(selected="runs")


# ---------------- look and feel ----------------
THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.teal,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    radius_size=gr.themes.sizes.radius_md,
).set(
    body_background_fill="*neutral_50",
    body_background_fill_dark="*neutral_950",
    block_background_fill="white",
    block_background_fill_dark="*neutral_900",
    block_border_width="0px",
    block_shadow="none",
    block_shadow_dark="none",
    block_label_background_fill="transparent",
    block_label_background_fill_dark="transparent",
    block_label_border_width="0px",
    block_label_shadow="none",
    button_primary_background_fill="*primary_700",
    button_primary_background_fill_hover="*primary_800",
    button_primary_background_fill_dark="*primary_600",
    button_primary_background_fill_hover_dark="*primary_500",
    button_primary_text_color="white",
    button_primary_text_color_dark="white",
    checkbox_background_color_selected="*primary_700",
    checkbox_background_color_selected_dark="*primary_600",
    checkbox_border_color_selected="*primary_700",
    checkbox_border_color_selected_dark="*primary_600",
)

HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500&display=swap" '
        'rel="stylesheet">')

CSS = """
footer{display:none !important}
.gradio-container{max-width:1560px !important;margin:0 auto !important}

/* app bar */
.appbar{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:6px 2px 10px}
.appbar h1{margin:0;font-size:21px;font-weight:650;letter-spacing:-.015em;color:var(--body-text-color)}
.appbar p{margin:3px 0 0;font-size:13.5px;color:var(--body-text-color-subdued)}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{font-size:12.5px;padding:5px 11px;border-radius:999px;color:var(--body-text-color-subdued);
      background:var(--block-background-fill);border:1px solid var(--border-color-primary)}
.chip-warn{color:#b45309;border-color:color-mix(in srgb,#d97706 45%,transparent);
           background:color-mix(in srgb,#d97706 10%,var(--block-background-fill))}

/* the two working areas */
/* Gradio drops elem_classes on columns, so the sidebar is found by what it holds */
.column:has(> #upload-audio){background:var(--block-background-fill);border:1px solid var(--border-color-primary);
       border-radius:14px;padding:6px 16px 16px !important;gap:8px !important}
.column:has(> #upload-audio) > .block:not(#upload-audio):not(#upload-ref), .column:has(> #upload-audio) > .block .block{
       padding-left:0 !important;padding-right:0 !important;background:transparent !important}
.html-container{padding:0 !important}
.block:has(> .html-container > .prose:empty){display:none !important}
.column:has(.transcript-title){gap:0 !important}
.section-title{font-size:11.5px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;
               color:var(--body-text-color-subdued);padding:12px 0 2px;border-top:1px solid var(--border-color-primary)}
.first-title .section-title{border-top:0;padding-top:6px}
.action-note{font-size:12px;color:var(--body-text-color-subdued);margin:0}
.transcript-title{font-size:13px;font-weight:600;color:var(--body-text-color);padding:2px 2px 8px}

/* compact upload boxes: small while empty, full size once there is a player to show */
#upload-audio:has(.upload-container){height:112px !important;min-height:0 !important;overflow:hidden}
#upload-audio .upload-container, #upload-audio .upload-container .wrap, #upload-ref .upload-container,
#upload-ref .upload-container .wrap{min-height:0 !important;font-size:.85rem;line-height:1.3}
#upload-audio .upload-container .wrap, #upload-ref .upload-container .wrap{padding-top:18px}
#upload-audio .icon-wrap, #upload-audio .or, #upload-ref .icon-wrap, #upload-ref .or{display:none !important}
#upload-audio, #upload-ref{border:1px dashed var(--border-color-primary) !important;border-radius:10px;
                           background:var(--background-fill-secondary) !important}

/* step list: one tidy column instead of bordered pills */
#steps .wrap{display:flex;flex-direction:column;gap:2px}
#steps label{background:transparent !important;border:0 !important;box-shadow:none !important;
             padding:4px 0 !important;width:100%;font-size:13.5px}

/* status */
.status{padding:10px 14px;border-radius:10px;font-size:13.5px;border:1px solid var(--border-color-primary);
        color:var(--body-text-color);background:var(--block-background-fill)}
.status-ok{border-color:color-mix(in srgb,#0d9488 45%,transparent);
           background:color-mix(in srgb,#0d9488 9%,var(--block-background-fill))}
.status-error{border-color:color-mix(in srgb,#dc2626 50%,transparent);
              background:color-mix(in srgb,#dc2626 9%,var(--block-background-fill))}

/* score cards */
.score{background:var(--block-background-fill);border:1px solid var(--border-color-primary);border-radius:14px;
       padding:14px 16px}
.score-title{font-size:14px;font-weight:600;color:var(--body-text-color);margin-bottom:10px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.metric{padding:10px 12px;border-radius:10px;background:var(--background-fill-secondary)}
.metric-label{font-size:12px;color:var(--body-text-color-subdued)}
.metric-value{font-size:24px;font-weight:650;letter-spacing:-.02em;color:var(--body-text-color);
              font-variant-numeric:tabular-nums;line-height:1.3}
.metric-main .metric-value{color:var(--color-accent)}
.metric-hint{font-size:11.5px;color:var(--body-text-color-subdued)}
.terms{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:12px}
.terms-label{font-size:12px;color:var(--body-text-color-subdued);margin-right:4px}
.term{font-family:"IBM Plex Sans Arabic","Segoe UI",sans-serif;font-size:13px;padding:2px 9px;border-radius:999px;
      color:var(--body-text-color);background:color-mix(in srgb,#0d9488 12%,var(--block-background-fill))}
.term-miss{background:color-mix(in srgb,#d97706 15%,var(--block-background-fill))}
.term b{font-family:Inter,system-ui,sans-serif;font-weight:500;font-size:11.5px}
.score-note{font-size:12px;color:var(--body-text-color-subdued);margin:10px 0 0;line-height:1.5}
"""

# ---------------- UI ----------------
calls = example_calls()
ready_count = sum(is_ready(m) for m in models.MODELS)

with gr.Blocks(title="Egyptian Arabic ASR Comparison") as demo:
    gr.HTML(render.header_html(ready_count, len(models.MODELS), ALLOW_CLOUD))
    hist_state = gr.State([])

    with gr.Row(equal_height=False):
        with gr.Column(scale=4, min_width=340):
            gr.HTML(render.section("Call"), elem_classes="first-title")
            example = gr.Dropdown(calls, value=None, label="Example call", visible=bool(calls),
                                  info="Its reference transcript is matched by the recording id.")
            audio = gr.Audio(type="filepath", label="Call audio", elem_id="upload-audio")
            ref_file = gr.File(label="Reference transcript (JSON or SRT, optional)",
                               file_types=[".json", ".srt", ".txt"], height=80, elem_id="upload-ref")
            ref_status = gr.Markdown("")

            gr.HTML(render.section("Model"))
            model = gr.Dropdown(model_choices(), value=default_model(), label="Model", show_label=False,
                                container=False)

            gr.HTML(render.section("Preprocessing"))
            use_pre = gr.Checkbox(value=False, label="Apply preprocessing")
            steps = gr.CheckboxGroup([(v, k) for k, v in STEPS.items()], value=[], label="Steps", show_label=False,
                                     elem_id="steps", container=False)
            gr.HTML('<p class="action-note">Only the model hears the processed audio. More steps can lower accuracy, '
                    'so compare runs with and without them.</p>')

            with gr.Accordion("Advanced", open=False):
                use_diar = gr.Checkbox(value=True, label="Speaker diarization (pyannote community-1)",
                                       info="Off = VAD-only segments, no agent/customer split.")
                speakers = gr.Radio(["2", "2 or 3 (IVR as a 3rd voice)"], value="2", label="Number of voices")
                swap = gr.Checkbox(value=False, label="Swap agent / customer (if the automatic mapping is wrong)")
                include_ivr = gr.Checkbox(value=False, label="Score the IVR lines too")
                show_blank = gr.Checkbox(value=False, label="Show segments with no text")
                prompt = gr.Textbox(models.DEFAULT_PROMPT, lines=2, label="Domain prompt (Whisper + prompt models only)")

            btn = gr.Button("Transcribe", variant="primary", size="lg")
            btn_all = gr.Button("Run all ready models", variant="secondary")
            if ALLOW_CLOUD:
                gr.HTML('<p class="action-note">Run all includes the cloud models, which send the audio out and '
                        'use your credits.</p>')

        with gr.Column(scale=9, min_width=320):
            status = gr.HTML("")
            score_view = gr.HTML("")
            with gr.Tabs() as tabs:
                with gr.Tab("Transcripts", id="transcripts"):
                    with gr.Row(equal_height=False):
                        with gr.Column(min_width=300):
                            gr.HTML('<div class="transcript-title">Reference</div>')
                            ref_view = gr.HTML(render.empty("Add a call to see its reference transcript."))
                        with gr.Column(min_width=300):
                            gr.HTML('<div class="transcript-title">Model output</div>')
                            model_view = gr.HTML(render.empty("Run a model to see its transcript here."))
                    files = gr.File(label="Download this run (JSON + SRT)", file_count="multiple", interactive=False,
                                    visible=False)
                with gr.Tab("All runs", id="runs"):
                    hist_table = gr.Dataframe(headers=HIST_HEADERS, value=[], interactive=False, wrap=True,
                                              label="This session (also saved to results/runs.csv)")
                with gr.Tab("Models", id="models"):
                    gr.Dataframe(headers=["Model", "Environment", "Status", "Notes"], value=models_table(),
                                 interactive=False, wrap=True, show_label=False,
                                 column_widths=["34%", "11%", "18%", "37%"], max_height=900)
                    gr.Markdown("To install a local model, run `./setup_envs.sh <environment>` in Git Bash and restart "
                                "the app.")
                    if not ALLOW_CLOUD:
                        gr.Markdown("Cloud models are disabled: real customer audio must not leave our servers.")

    # Keep the switch and its steps in step, in the browser so the ticks appear instantly.
    # Gradio reads a js return value as a list with one item per output, hence the outer brackets.
    use_pre.input(None, use_pre, steps, js=f"(on) => [on ? {json.dumps(runnable_steps())} : []]")
    steps.input(None, steps, use_pre, js="(selected) => [selected.length > 0]")
    example.change(pick_example, example, [audio, ref_file])
    audio.change(show_reference, [audio, ref_file], [ref_view, ref_status])
    ref_file.change(show_reference, [audio, ref_file], [ref_view, ref_status])
    inputs = [audio, ref_file, model, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr, show_blank,
              hist_state]
    btn.click(run, inputs, [status, ref_view, model_view, score_view, files, hist_state, hist_table])
    btn_all.click(run_all, [audio, ref_file, use_pre, steps, use_diar, speakers, prompt, swap, include_ivr,
                            show_blank, hist_state], [status, hist_state, hist_table, tabs])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name=os.environ.get("ASR_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("ASR_PORT", "7860")),
        share=False,                           # never publish real calls on a public gradio.live link
        allowed_paths=[str(DATA_DIR)],
        theme=THEME,
        css=CSS,
        head=HEAD,
    )
