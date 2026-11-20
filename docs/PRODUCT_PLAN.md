# Call Intelligence Platform: product and technical plan

A full customer-service call platform: transcription with our own Egyptian Arabic model, analysis of every call,
dashboards, customer and agent views, recommended actions with follow-up tracking, and a built-in assistant that
answers questions about the calls. It is built in `HassnaaElshafei2/call_center_asr`, runs on the company's
DGX Spark models, and sends no call audio or text to outside services.

Status: plan only. Nothing here is built yet.

---

## 0. Decisions (20 Nov 2026)

| Topic | Decision |
|---|---|
| Enterprises | One app for **ADIB and B.TECH**, with an **enterprise switcher** (section 0.1) |
| Users | **All roles from the start**: managers, QA/supervisors, retention team, agents, executives, admin |
| Model API | `https://llm-api.gcp.trysia.ai/api`, key in the `LLM_API_KEY` environment variable (never in the repo). Tested: section 0.2 |
| Transcription model | Built against an **ASR service interface**; when Mohammed's model is hosted on the DGX, only its URL changes (section 0.3) |
| Customer identity | No customer file exists: identity comes from **file names and the call itself** (section 0.4) |
| Look | **Sia branding, like sia-prime** (section 0.5) |

### 0.1 Enterprises

- An **enterprise switcher** in the header (logo + name, like a workspace switcher): *ADIB*, *B.TECH*, and *All
  enterprises* for users who may see both. The choice is part of the URL (`/e/btech/overview`), so links open in
  the right enterprise.
- Every record carries `enterprise_id`: calls, customers, agents, teams, queues, categories, scorecards, actions,
  alerts. Every API query is filtered by the enterprise the user has selected **and** is allowed to see.
- Each enterprise has its **own** call categories (banking vs electronics retail), scorecard, queues, file-name
  rules, recommended-action types and offer templates, and an accent colour/logo inside the Sia look.
- **All enterprises** view: side-by-side KPIs (resolution, satisfaction, handle time) and the same charts split by
  enterprise. The assistant also takes the enterprise as a filter («قارن بين أديب وبي تك في المكالمات اللي متحلتش»).
- Roles are given **per enterprise** (for example QA for B.TECH only, manager for both).

### 0.2 Model API (tested from here)

The DGX models are served through an Open WebUI gateway (vLLM behind it), OpenAI-compatible under `/api`:

| Endpoint | Model | Test result |
|---|---|---|
| `POST /api/chat/completions` | `qwen3.6-35b` (262k context) | Egyptian Arabic answers ✅; **must send `chat_template_kwargs: {"enable_thinking": false}`**, otherwise it reasons first and uses the token budget; structured JSON with a strict schema ✅; tool calling ✅ («كام مكالمة متحلتش الأسبوع ده في بي تك؟» → `aggregate_calls(enterprise=BTECH, resolution=not_resolved, period=last_7_days)`) |
| `POST /api/embeddings` | `qwen3-embedding-4b` | ✅ 2,560-dimension vectors, Arabic and English |
| `GET /api/models` | | Lists only these two models today |

Not exposed yet: **Qwen3-Reranker-4B** and **Gemma 4 26B** (both off). The plan works without them: search
re-ranking falls back to embeddings only (or a short Qwen re-rank), and the "second opinion" becomes a second Qwen
pass with a different prompt until Gemma is available.

Security: the key was shared in chat, so **rotate it** before production; the app reads it only from the
environment, and the gateway is called only from the backend (never from the browser).

### 0.3 Transcription without waiting for the DGX

- The backend talks to transcription through one small interface: `POST /transcribe` (audio → text + confidence),
  `POST /diarize` (audio → speaker turns).
- **Now:** we ship that ASR service ourselves (FastAPI + Mohammed's model + pyannote, one Docker image), runnable on
  any GPU machine (or CPU for a slow demo). Configured by `ASR_SERVICE_URL`.
- **Later:** when the platform team hosts the model on the DGX, `ASR_SERVICE_URL` points there. Nothing else changes.
- Decoding settings are those from our evaluation (beam 8, length cap 12 tokens/s + 20, no length penalty), which
  removed the runaway repeats.

### 0.4 Customer identity without a customer file

What the data shows:

- **B.TECH file names are the customer's phone number**, in three formats:
  `btech_01272729111` (local mobile), `btech_201029240321` (country code 20 + mobile without its 0),
  `btech_1000470080` (mobile without its 0). All normalise to one form, `+20 10 2924 0321`.
- **ADIB file names are recording IDs**, not phone numbers: `20240812 000121 849…` starts with the date and time; the
  rest is a system ID (possibly with an extension). They identify the call, not the customer.
- Inside the calls, customers often say their **name** («معاك كريم»), and sometimes a **phone number** or card digits.

The approach, in order of trust:

1. **File-name rules per enterprise** (configurable patterns): phone → normalised Egyptian number. B.TECH works this
   way today. A customer CSV or CRM export can be imported later and matched on the same number.
2. **From the transcript**: the analysis step extracts the customer's name and any spoken phone/account digits (number
   words converted to digits), each with a confidence.
3. **Matching**: same phone → same customer automatically. Name only → a *possible match* that a person confirms
   ("Is this the same Karim as on 12 Aug?"). Nothing found → the call gets its own unidentified customer, still
   fully analysed.
4. Admins can merge and split customers; every change is audited.
5. Privacy: phone numbers stored as a keyed hash plus a masked form (`+20 10 •••• 0321`); the full number only for
   permitted roles, with an audit entry.

Effect: Customer 360 and repeat-call detection work fully for B.TECH from day one; for ADIB they work when a number
is said or a customer file is imported, and otherwise per call.

### 0.5 Look and feel (Sia, like sia-prime)

- Sia Prime tokens: cream light theme (`--bg #f6f1e7`, panels `#fffdf8`) and true-black dark theme, Sia violet brand
  (`#5516fb`, dark `#6a33ff`), radii 8–20 px, soft shadows, light grain; Inter for the interface, **Noto Sans Arabic**
  for Arabic text; the self-drawing Sia mark on the landing/sign-in page.
- Theme switch and widget→pop-up morphs with View Transitions, reduced motion respected (the sia-prime `theme.ts`
  approach).
- Status colours with shapes as well (resolved ✓, partly ◐, not resolved ✕) so they read without colour.
- Right-to-left for Arabic text blocks inside a left-to-right interface; Arabic or English interface text later.

### 0.6 Demo data available today

- **Real calls**: 5 ADIB and 14 B.TECH full recordings with Gemini turn labels.
- **Synthetic calls**: our 76 ElevenLabs calls (`hs01`–`hs76`, ADIB and B.TECH scenarios, with scripts), useful to
  fill the dashboards and to test the analysis against known scripts (invented names and numbers only).

---

## 1. What we learned from the existing repos

| Repo | What it is | What we take from it |
|---|---|---|
| **sia-call-center** | Call scoring and review: upload, transcribe (OpenRouter Whisper/Gemini), score against a scorecard, supervisor review | The reliable ingestion pipeline (storage, queue, worker, retries, outbox), versioned scorecards, KPI evidence quotes, review overrides, masked phone numbers, safe CSV export. Missing: resolution, satisfaction, customer view, actions, independent chatbot, our ASR model |
| **global-it-poc** (Intelligence Console) | Payment and fraud console in Next.js | **Ask pattern**: the model turns a question into a query plan, the plan is checked against a schema, the app runs it on the real data, so **the model never invents a number**. The plan is shown as removable chips. Built-in keyword reading in Arabic and English when the model is down. Filters stored in the URL, so every view can be shared. Summary / Full switch. Every case has a brief with key evidence and "do now" actions, each finding has an owner |
| **iskraemeco** (Plant map) | 3D plant dashboard with a plant assistant | **Assistant pattern**: a round launcher opens a chat window; the assistant uses tools and **knows what is on screen** (open chart, filters, numbers); replies carry action buttons ("Show … on the map"); summaries are written from facts the page computed, so the model can't add a number the chart doesn't have; fallback answers without the model; one retry on a slow provider. Notifications grouped into summary cards, a bell with filters. Accessibility: status shown by shape as well as colour, reduced motion respected |
| **sia-prime** (Merchant intelligence) | Bank merchant map with scores and next steps (React + Vite) | Premium feel: animated landing, light and dark themes, View Transitions. KPI tiles with a comparison line, **every widget opens a large pop-up** with summary, charts, tables and actions, "What Prime sees" insight list, **one next best step per entity** with counts and "Show on map", campaign lists and CSV export, Arabic and English search, guided tour. Its chat is planned but not built |

**Design direction:** the sia-prime look and feel (cards, pop-ups, light/dark, motion), the global-it-poc rule that
every number comes from data and every view is a shareable URL, and the iskraemeco assistant behaviour (tools,
screen awareness, action buttons, graceful fallback).

---

## 2. Who uses it and what they need

| Person | Main question | Where they live in the app |
|---|---|---|
| CX / call-centre manager | How are we doing, what is getting worse, where do we lose customers? | Overview, Insights, reports |
| Supervisor / QA | Which calls need attention, which agents need coaching? | Calls, review queue, agents |
| Retention / sales team | Which customers should we call back or make an offer to? | Action Center, at-risk customers |
| Agent | How am I doing, what should I improve? | My performance (own view only) |
| Executive | One-page picture and the money at stake | Weekly brief, Overview summary |
| Admin | Users, scorecards, categories, data retention | Settings |

---

## 3. Features

Marked **MVP** (first usable version), **V1** (complete product) or **V2** (later).

### 3.1 Transcription service (the core)

- **Ingestion** (MVP): upload one or many recordings in the browser; a watched storage folder for bulk/telephony drops
  (V1); API upload for integrations (V1). Metadata from file names or a CSV: agent, queue, customer phone, time.
- **Pipeline** (MVP), each step a visible status with retries:
  1. Normalise audio (mono, 16 kHz, loudness).
  2. Voice activity detection and **speaker diarization** (pyannote) into turns.
  3. **Speaker roles**: agent vs customer vs IVR (greeting cues, channel if stereo, the LLM as tie-breaker).
  4. **ASR with Mohammed's fine-tuned Cohere model** per turn (beam 8, output length capped by duration, which removes
     runaway repeats; the settings from our evaluation).
  5. Transcript quality check: empty or looping output, very low confidence → flagged, not silently analysed.
- **Transcript view** (MVP): audio player with waveform and speaker lanes, transcript synced to playback (click a
  line to jump), right-to-left Arabic text, search inside the call, download (TXT/JSON/SRT).
- **Corrections** (V1): a reviewer can fix a transcript line; corrections are stored and become new training data
  (section 6, the data flywheel).
- **Privacy** (MVP): phone numbers masked on screen, card/account numbers in transcripts masked, full values only for
  permitted roles with an audit entry (as in sia-call-center).

### 3.2 Call analysis (per call)

One structured analysis per call from **Qwen3.6-35B**, every label with **evidence quotes and timestamps** from the
transcript. Numbers that can be measured from audio or timestamps are computed, not guessed by the model.

| Output | Values | Business use |
|---|---|---|
| **Resolution** (MVP) | Resolved / Partly resolved / Not resolved, with the reason and the quote | First-call resolution rate, unresolved follow-up |
| **Customer satisfaction (predicted)** (MVP) | 1–5 with the signals behind it | Satisfaction trend without surveys; calibrated later against real survey scores |
| **Atmosphere / sentiment journey** (MVP) | Start, middle, end mood (calm, confused, frustrated, angry, happy); peaks with timestamps | Spot calls that went bad and where |
| **Reason and topic** (MVP) | From an editable category list (banking: cards, InstaPay, Fawry, deposits…; B.TECH: installation, delivery, instalments…) | Top contact drivers |
| **Summary** (MVP) | 3–5 lines, Arabic or English | Fast review |
| **Agent quality scorecard** (MVP) | Versioned KPIs (greeting, verification, empathy, accuracy, closing), pass/fail with quotes | QA without listening to every call |
| **Measured behaviour** (MVP) | Talk/listen ratio, silences, hold time, interruptions, speaking speed, call length | Coaching facts that need no model |
| **Risk flags** (V1) | Churn risk, escalation/complaint risk, compliance breach (no verification, sensitive data said aloud) | Alerts and priority |
| **Promises made** (V1) | "We will call you tomorrow", "the technician comes Saturday", with due dates | Commitments tracker; broken promises are a top cause of repeat calls |
| **Opportunity** (V1) | Upsell / cross-sell moment (asked about a product, eligible offer) | Revenue from service calls |
| **Knowledge gap** (V1) | Questions the agent couldn't answer | Training and knowledge-base articles |
| **Customer effort** (V2) | Transfers, repeated explanations, hold | Effort score |

**Second opinion** (V1): **Gemma 4 26B** re-checks high-impact labels (Not resolved + angry, compliance breach, low
predicted satisfaction). Disagreements go to the human review queue instead of being shown as certain.

### 3.3 Overview and insights

- **KPI tiles** (MVP): calls, resolution rate, predicted satisfaction, share of negative calls, average handle time,
  escalations, open actions; each with change vs the previous period.
- **Charts** (MVP): resolution and satisfaction over time, top reasons, unresolved by reason, sentiment by queue/team,
  calls by hour × weekday heatmap, agent ranking.
- **"What we see"** (MVP): 3–5 written insights. The app computes the facts; the model only writes them as sentences
  (the iskraemeco rule), with links that open the matching calls.
- **Every widget opens a pop-up** (V1): summary, larger chart, table, and actions (sia-prime pattern).
- **Filters in the URL** (MVP): date range, company/queue, team, agent, reason, resolution, sentiment, satisfaction,
  duration, risk. **Saved views** (V1). **Summary / Full** switch (V1).
- **Trend alerts** (V1): a topic suddenly rising (for example "card blocked" doubles today) raised as an early
  warning of a product or system problem.

### 3.4 Calls explorer and call detail

- **Calls table** (MVP): all the filters above, columns for resolution, satisfaction, sentiment, reason, agent,
  duration, flags; bulk select → create actions or export.
- **Call detail** (MVP): player + synced transcript, sentiment timeline, **key moments** (problem stated, escalation,
  resolution, promise), summary, resolution with evidence, scorecard, measured behaviour, **actions panel**.
- **Review queue** (V1): calls needing a human (low confidence, model disagreement, compliance flags); approve or
  correct labels, every change audited.

### 3.5 Customers (Customer 360)

- **Customer page** (V1): all calls of one customer (by hashed phone/ID), satisfaction trend, open issues, promises
  due, risk, actions taken and their outcome.
- **At-risk list** (V1): unhappy and unresolved customers, repeat callers (called again within N days about the same
  issue), customers with a broken promise.
- **Repeat-call detection** (V1): the true first-call resolution rate, computed across calls.

### 3.6 Agents and coaching

- **Agent list and page** (MVP): calls, resolution rate, satisfaction, scorecard trend, behaviour metrics, vs team.
- **Coaching cards** (V1): 2–3 specific points per agent with the call moments that show them (click to listen);
  supervisor marks them discussed.
- **My performance** (V2): agents see only their own page.
- **Wellbeing signal** (V2): an agent's own tone and handle time trending down over weeks (burnout early warning).

### 3.7 Action Center (close the loop)

The step from "knowing" to "doing", and where most of the business value is.

- **Recommended actions per call** (MVP): call the customer back, send an offer or compensation, escalate to a
  supervisor, open a ticket, schedule a technician, coach the agent; each with why (the evidence) and a priority.
- **Action board** (V1): owner, due date, status (open → in progress → done), outcome (customer satisfied again,
  offer accepted, no answer). Bulk actions from any filtered list.
- **Offer and message drafts** (V1): the model drafts a callback script or an SMS/WhatsApp message in Egyptian Arabic
  from the call; **a person always approves before anything is sent**. Sending through company channels is an
  integration step (V2).
- **Outcome tracking and ROI** (V1): recovered customers, accepted offers, repeat calls avoided, shown on the Overview.
- **Campaign lists** (V1): "all unresolved installation complaints this week" → list → CSV or the action board.

### 3.8 Ask: the assistant (independent, no Brain)

A round launcher on every page opens a chat panel; a full-page version for longer sessions.

- **How it answers** (MVP): a tool-using agent on **Qwen3.6-35B** with these tools:

  | Tool | What it does |
  |---|---|
  | `query_calls` | Filters + sort + limit over calls (resolution, sentiment, satisfaction, reason, agent, customer, dates) |
  | `aggregate` | Counts, rates, averages, group by (agent, reason, day, queue) |
  | `get_call` | One call: summary, labels, evidence, transcript excerpt |
  | `search_transcripts` | Meaning-based search over transcripts (Qwen3-Embedding-4B + Qwen3-Reranker-4B) |
  | `get_customer` / `get_agent` | Profile, history, trends |
  | `create_action` | Proposes an action; the user confirms with a button |

- **Grounded numbers** (MVP): every figure comes from a tool result, never from the model's memory (global-it-poc
  rule). Tools run on read-only views with row limits; no free-form SQL from the model.
- **Shows its reading** (MVP): the filters it used appear as chips ("Not resolved · last 7 days · B.TECH"), removable,
  plus an "Open these 23 calls" button that opens the Calls page with the same filters.
- **Knows the screen** (V1): it receives the current page, filters and selected call, so "why was this call bad?" or
  "compare this agent with the team" work (iskraemeco pattern).
- **Citations** (MVP): answers about specific calls link to them and quote the moment.
- **Arabic and English** (MVP), including Egyptian Arabic questions.
- **Fallback** (V1): built-in answers for the most common questions when the model is unavailable.
- Example questions: «إيه أكتر سبب للمكالمات اللي متحلتش الأسبوع ده؟», "Which customers were unhappy and still have no
  callback?", "Which agent improved most this month?", "Show calls where the customer asked to cancel."

### 3.9 Alerts and reports

- **Alerts** (V1): very negative call, compliance breach, VIP customer unresolved, broken promise due today;
  bell with filters, grouped summary cards, optional email.
- **Daily / weekly brief** (V1): generated from computed facts, PDF or email: what changed, top problems, actions due,
  recovered customers.

### 3.10 Administration

- Users and roles (MVP: admin, manager, supervisor, viewer; V2: agent self-view), audit log of every view of full
  phone numbers and every label change (V1), scorecard editor with versions (V1), category editor (V1), data
  retention rules (V1), API keys for integrations (V2).

### 3.11 More ideas with business value (to choose from)

| Idea | Value |
|---|---|
| Cost of unresolved calls (repeat calls × cost per call) | Puts a money figure on resolution |
| Script and compliance adherence per queue | Lower regulatory risk (banking) |
| Peak-hour and staffing insight (volume and difficulty by hour) | Better scheduling |
| Knowledge-base suggestions from knowledge gaps | Faster answers, shorter calls |
| Product / system issue early warning (topic spikes) | Fix root causes before calls pile up |
| Best-practice clips: top agents' handling of hard calls | Training library |
| Team / branch benchmarking | Healthy competition, targeted coaching |
| Survey calibration: compare predicted satisfaction with real CSAT when available | Trust in the numbers |

---

## 4. Architecture

```
Browser (React)
   │  /api, /assistant (streaming)
   ▼
API (FastAPI) ── PostgreSQL + pgvector (calls, turns, analysis, actions, embeddings)
   │                 ▲
   ├── Object storage (recordings; private, signed URLs)
   └── Job queue ──► Workers
                       ├── Audio + diarization worker (pyannote)
                       ├── ASR worker ──────────► ASR service (Mohammed's Cohere model)  ┐
                       ├── Analysis worker ─────► Qwen3.6-35B, Gemma 4 26B               │ DGX Spark
                       └── Indexing worker ─────► Qwen3-Embedding-4B, Qwen3-Reranker-4B  ┘
Assistant (in the API) ─ tools over read-only views ─► Qwen3.6-35B
```

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript, TanStack Query, ECharts, design tokens with light/dark, RTL-aware text | Same stack as sia-call-center and sia-prime; ECharts handles heatmaps and timelines |
| API | FastAPI (Python 3.12), Pydantic, SQLAlchemy, Alembic | Same as sia-call-center; Python for the ML side |
| Database | PostgreSQL with pgvector | One database for data and transcript search |
| Jobs | Redis + a worker library (arq or Celery) | Retries, priorities, progress |
| Storage | S3-compatible (GCS or MinIO) | Recordings stay private |
| Auth | Email + password with JWT first; company Google sign-in later | As the other Sia apps |
| Deployment | Docker Compose first (like sia-call-center), then the company's GCP setup | |

### Models (all on the DGX Spark)

| Job | Model | Notes |
|---|---|---|
| Transcription | **Mohammed's fine-tuned Cohere Transcribe Arabic** (2B, ~5–6 GB) | Needs to be added to the DGX model list as a service (it isn't there today) |
| Speaker separation | pyannote (small, GPU or CPU) | Also needs a service |
| Call analysis, assistant, summaries, drafts | **Qwen3.6-35B** (`qwen3.6-35b`, already running) | 262k context fits whole calls; tool calling for the assistant |
| Second opinion on high-impact labels | **Gemma 4 26B** (`gemma4-26b`, currently off and not on the gateway) | Until it is available: a second Qwen pass with a different prompt |
| Transcript search | **Qwen3-Embedding-4B** (on the gateway) + **Qwen3-Reranker-4B** (not on the gateway yet) | Arabic and English; embeddings alone until the reranker is exposed |
| Not needed | Whisper large-v3-turbo, PaddleOCR-VL | Our Cohere model is much better than Whisper on these calls |

Memory check: Qwen3.6-35B 70 GiB + embedding 10.3 + reranker 12 + Cohere ~6 + pyannote ~2 ≈ 100 GiB of the 121.7 GiB
(8 kept free). Gemma 4 (27 GiB) does **not** fit at the same time: either run it on demand or skip the second opinion.

---

## 5. Data model (main tables)

| Table | Holds |
|---|---|
| `calls` | Recording, company/queue, agent, customer, time, duration, pipeline status |
| `turns` | Speaker, role, start/end, text, ASR confidence |
| `analyses` | Versioned analysis per call (model, prompt version), resolution, satisfaction, sentiment journey, reason, summary, flags |
| `evidence` | Label → quote + timestamps |
| `scorecards`, `scorecard_kpis`, `call_kpi_results` | Versioned QA scorecards and results (as sia-call-center) |
| `customers` | Hashed identifier, masked phone, aggregates |
| `agents`, `teams`, `queues` | Organisation |
| `promises` | Commitment, due date, kept / broken |
| `actions`, `action_events` | Recommended and created actions, owner, status, outcome, history |
| `alerts` | Rule, call, status |
| `corrections` | Human transcript and label fixes (training data) |
| `turn_embeddings` | pgvector embeddings for search |
| `users`, `roles`, `audit_log` | Access and audit |

---

## 6. Quality and the data flywheel

- **ASR**: keep the 2 held-out ADIB calls and add new held-out calls; WER per release (our evaluation notebook).
- **Analysis labels**: a human-labelled set of 50–100 calls (resolution, satisfaction, reason) to measure the model's
  accuracy before showing labels as facts; re-run on every prompt or model change.
- **Assistant**: a test list of 50 questions with expected answers, run automatically.
- **Flywheel**: transcript corrections and reviewed labels flow into a dataset; periodic re-fine-tuning of the ASR
  model and prompt improvements, measured on the same held-out sets.

---

## 7. Phases (order of work)

1. **Foundations**: repo structure, Docker Compose, database and migrations, auth, design system (tokens, cards,
   pop-up, table, chart wrappers, light/dark, RTL), storage, job queue.
2. **Transcription service**: ASR service around Mohammed's model, diarization and roles, pipeline with statuses,
   upload, transcript view with synced player. *First demo: upload a call, read it.*
3. **Call analysis**: prompt and JSON schema with evidence, measured behaviour, scorecards; label evaluation set.
4. **Calls explorer, call detail, Overview** with filters in the URL and "What we see".
5. **Assistant** (tools, chips, citations, open-these-calls), then screen awareness.
6. **Action Center**: recommended actions, board, drafts with approval, outcomes and ROI.
7. **Customers and agents**: Customer 360, repeat calls, coaching cards.
8. **Alerts, reports, review queue, admin**, then integrations (telephony, CRM, messaging).

**MVP = phases 1–5** plus recommended actions on the call page.

---

## 8. Open questions and risks

| Question / risk | Why it matters | Proposal |
|---|---|---|
| How do we call the DGX models (URL, API format, keys, rate limits)? | Everything depends on it | Confirm with the platform team; assume an OpenAI-compatible API behind `models.gcp.trysia.ai` |
| Can Mohammed's Cohere model and pyannote be added to the DGX model list? | Transcription is the core | Package them as small services the platform can run |
| Real call data: volume, metadata (agent ID, customer phone, queue) | Customer view and repeat calls need a customer ID | Agree on a file-name or CSV convention |
| Accuracy of predicted resolution/satisfaction | Wrong labels erode trust | Evaluation set, evidence quotes, second opinion, review queue, "predicted" wording |
| Privacy (banking data) | Regulatory | Everything on company infrastructure, masking, roles, audit, retention |
| ASR accuracy (~36% WER on the hardest test calls) | Analysis quality depends on it | Analysis prompts that tolerate errors, corrections loop, more real training data |
| GPU memory on the DGX | Gemma doesn't fit with the rest | On-demand second opinion |

---

## 9. Still open

1. **Where the ASR service runs until the DGX hosts it**: a company GPU machine is best; CPU works for a slow demo
   (Mohammed's README: about 9 GB RAM, slow but fine for a few clips).
2. **Where the app is deployed** (company GCP, domain, sign-in method), needed before the first shared demo.
3. **Human-labelled evaluation calls**: someone from the team to label resolution / satisfaction / reason for
   50–100 calls, so the analysis can be measured before managers rely on it.
4. **Reranker and Gemma 4** on the gateway (optional; the app works without them).
