# Sia Call Intelligence

Customer-service call analysis for **ADIB Egypt** and **B.TECH** (switch between them, or see both side by side).
Recordings are transcribed by Mohammed's fine-tuned Cohere model. Each call is then analysed by the models on the DGX gateway, giving:

- what the call was about;
- whether the problem was **resolved / partly resolved / not resolved**;
- **predicted satisfaction** (1–5);
- how the customer's mood changed;
- the QA scorecard, promises made and risks;
- suggested follow-ups (callback, offer, escalation…) that a person approves.

| Page | What it is for |
|---|---|
| Overview | KPIs against the previous period, trend, outcomes, mood journey, reasons, agents, call heat map, enterprises side by side. Every chart opens the calls behind it |
| Calls | Every call, with filters (period, outcome, reason, agent, satisfaction, mood, words said), CSV export and upload |
| Call detail | Player with speaker lanes, transcript (click to seek, correct a line), evidence for each label, QA, measured behaviour, review |
| Review queue | Calls the analysis is unsure about (second opinion disagrees, compliance, low transcript confidence) |
| Customers | Customer 360: every call of a customer, risk, open actions; possible duplicates to merge |
| Agents | Resolution, satisfaction, QA by item compared with the team, talk share, AI coaching notes |
| Action Center | Suggested → to do → in progress → done; message drafts in Egyptian Arabic; promises due |
| Weekly brief | One page for management, written from the period's numbers |
| Ask | Chat assistant (also a pop-up on every page): answers from your data with links to the calls, can propose actions |
| Administration | Users and roles per enterprise, call reasons, QA scorecard, agents, recording-name rules, audit log, system status |

Roles are set per enterprise: admin, manager, QA, retention, agent (sees only their own calls) and executive (read only).

## Run it with Docker

```bash
cp .env.example .env      # fill in LLM_API_KEY, JWT_SECRET, PHONE_HASH_KEY, ADMIN_PASSWORD, DEMO_PASSWORD
docker compose up -d --build
```

Open http://localhost:8000 and sign in as `ADMIN_EMAIL` / `ADMIN_PASSWORD`. These demo users can sign in with `DEMO_PASSWORD`:

- `manager@demo.sia`
- `qa@demo.sia`
- `retention@demo.sia`
- `exec@demo.sia`
- `btech.qa@demo.sia` (B.TECH only)

Optional: import the 76 synthetic demo calls. The worker analyses them in a few minutes.

```bash
docker compose exec app python -m callintel.manage demo /app/demo_data/scripts
```

### Transcription

Without `ASR_SERVICE_URL`, uploaded recordings are kept in a **waiting for transcription** state. Once a service is set, **Administration → System → Retry** sends them through. Two ways to provide it:

- **On a GPU machine, with this compose file:** put Mohammed's model folder in `ASR_MODEL_DIR`, set `ASR_SERVICE_URL=http://asr:9000`, then run `docker compose --profile asr up -d --build`.
- **On the DGX, once it hosts the model:** run `asr_service/` there (see its Dockerfile) and set `ASR_SERVICE_URL` to its address. Nothing else changes.

The service separates speakers in this order:

1. stereo channels, when each party is on its own channel;
2. otherwise pyannote, if `HF_TOKEN` is set;
3. otherwise voice activity only.

The backend then decides which speaker is the agent, the customer or the IVR from what each one says.

### How customers are identified

- **B.TECH:** recordings are named by the caller's phone (`01272729111`, `201029240321`, `1000470080`). The number is normalised to +20…, then stored as a keyed hash plus a masked form. Only manager, retention and admin can reveal the full number, and every reveal is written to the audit log.
- **ADIB:** recordings carry an ID. The customer is linked from a phone number said in the call.
- **Names alone are never matched automatically.** A name only gives a "possibly the same customer" suggestion, which a person merges.
- **Rules per enterprise:** Administration → Recording names takes regexes with a `(?P<phone>…)` group.

## Develop locally

You need Postgres 16, Python 3.12+ and Node 22.

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env                                  # fill it in; DATABASE_URL defaults to localhost
python -m callintel.manage init                          # migrate, create enterprises, reasons, scorecards, users
python -m callintel.manage demo ../demo_data/scripts     # optional demo calls
uvicorn callintel.main:app --reload                      # API on :8000 (also serves frontend/dist)
python -m callintel.worker                               # in another terminal: transcription, analysis, search
```

```bash
cd frontend
npm install
npm run dev                                              # http://localhost:5173, /api proxied to :8000
```

Tests use a separate database. Create `callintel_test` once, or set `TEST_DATABASE_URL`; its name must end in `_test`:

```bash
cd backend
python -m pytest -q
```

## How the analysis works

- One structured pass of `qwen3.6-35b` per call, in JSON mode. The answer is checked against a schema and asked again once if it doesn't fit. Every label cites the turns it is based on.
- A second, independent pass checks the high-impact labels: resolution, satisfaction and churn. When the two disagree, the call goes to the review queue. Set `LLM_SECOND_OPINION_MODEL` to use a different model for this pass, once the gateway offers one.
- Talk share, silences and talking over each other are **measured from the timings**, not guessed by the model.
- A repeat call is the same customer within 14 days, either about the same reason or after a call that wasn't fully resolved.
- Search embeds every turn with `qwen3-embedding-4b`. The Ask assistant and the transcript search use it.
- Corrections made in reviews are stored, so they can later measure the analysis and feed the next prompt version.

## Layout

```
backend/        FastAPI app, worker, analysis, Ask assistant (callintel/), Alembic migrations, tests
frontend/       React + TypeScript app (Vite), Sia design
asr_service/    transcription service for Mohammed's model (GPU)
demo_data/      76 synthetic call scripts used by the demo import
```
