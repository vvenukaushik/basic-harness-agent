# Harness-Engineered Banking Agent

A retail-banking chat agent built in four stages to show that reliability comes from
deterministic code around the agent (tools, policy layer, session state, audit log),
**not** from prompt tweaks or a stronger model. The system prompt and model stay frozen.

> All data is mock data. Do not type real personal information.

## Setup

```powershell
py -3.14 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then fill in GOOGLE_API_KEY
.venv\Scripts\adk web
```

## Model

Gemini 3.5 Flash-Lite on the free Google AI Studio tier, read from `MODEL_NAME`.
It is deliberately a weaker model: the point is that the harness, not the model, makes the agent reliable.

## Stages

| Stage | Tag | What it adds |
|---|---|---|
| 1 | `stage-1` | Baseline agent, no harness |
| 2 | `stage-2` | PolicyService enforces rules |
| 3 | `stage-3` | Human-in-the-loop confirm |
| 4 | `stage-4` | Audit log + session limit |

## Tests

```powershell
.venv\Scripts\pytest
```

## Deploy (Render free tier)

The same Docker image runs anywhere. `main.py` serves the ADK web UI behind `web_guard.py`:

- **Passcode:** HTTP Basic Auth from `DEMO_USER` / `DEMO_PASSWORD`. The app refuses to start without them.
- **Rate limit:** 20 agent requests per minute per IP, HTTP 429 beyond that.
- **Health check:** `/healthz` is the only path open without the passcode.
- **Secrets:** `GOOGLE_API_KEY` is set in the host's dashboard, never in the repo or image.

On Render: **New → Blueprint**, pick this repo, and fill in `GOOGLE_API_KEY`, `DEMO_USER` and
`DEMO_PASSWORD` when asked (`render.yaml` defines the rest). The free instance sleeps after
15 minutes idle, so the first visit takes up to a minute. Restarts reset sessions and balances.

Test the container locally:

```powershell
docker build -t basic-harness-agent .
docker run -p 8080:8080 --env-file .env -e DEMO_USER=demo -e DEMO_PASSWORD=change-me basic-harness-agent
# --env-file keeps quotes literally: write GOOGLE_API_KEY=abc, not GOOGLE_API_KEY='abc'
```

> **Viewer notice:** all data is mock data. Don't type real personal information; free-tier
> Gemini prompts may be used by Google for training.
