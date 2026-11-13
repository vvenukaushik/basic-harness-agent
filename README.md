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
