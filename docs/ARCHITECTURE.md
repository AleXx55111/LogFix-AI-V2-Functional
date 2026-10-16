# LogFix AI V2 architecture

```text
                       ┌─────────────────────────────────┐
                       │ React SPA (Vite)                │
                       │ Logs · Incidents · Ops Chat     │
                       │ Code Chat · Agents · Settings   │
                       └────────────────┬────────────────┘
                                        │ HTTPS REST JSON
                                        ▼
                       ┌─────────────────────────────────┐
                       │ FastAPI                         │
                       │ Public synthetic routes         │
                       │ Private X-Admin-Key routes      │
                       │ PUBLIC_DEMO_ONLY security lock  │
                       └──────────┬─────────────┬────────┘
                                  │             │
           ┌──────────────────────┘             └────────────────────────┐
           ▼                                                             ▼
  ┌──────────────────┐                                         ┌─────────────────┐
  │ Logs / incidents │                                         │ Repo intelligence│
  │ - demo fixtures  │                                         │ - demo fixtures │
  │ - Azure / AWS    │                                         │ - safe ZIP parse│
  │ - GCP SDK reads  │                                         │ - AST + grep    │
  └────────┬─────────┘                                         └─────────┬───────┘
           ▼                                                             ▼
  ┌──────────────────┐                                         ┌─────────────────┐
  │ Operations agents│                                         │ Code agents     │
  │ 11 stages        │                                         │ 7 stages        │
  └────────┬─────────┘                                         └─────────┬───────┘
           └──────────────────────┬──────────────────────────────────────┘
                                  ▼
                     ┌────────────────────────────┐
                     │ Evidence + source mapping  │
                     │ Local retrieval Q&A        │
                     │ Optional OpenAI synthesis  │
                     └────────────────────────────┘
```

Public sandbox loads only the built-in fabricated fixtures. A separately deployed private instance can query real sources after an administrator unlocks it and supplies non-secret resource selectors. No background ingestion, persistence, code execution or mutation.

## Data boundaries

- Ingestion: ≤100 log records per cloud, ≤300 total, 30-minute lookback; never place credential or token into the log response intentionally.
- Sanitize: heuristic password/token/PII redaction before processing and before any optional model request.
- Analyze: deterministic stages produce typed `AnalysisResult` with incident evidence and timing traces.
- Code analysis: in-memory imported ZIP; never extracted or executed; file and size limits.
- Correlate: keyword-based code touchpoint suggestions, not proven causal attribution.
- Browser: sample data public, private administration requires a key. The admin key stays in JS memory and cannot be shared with public demo visitors.
- Storage: API process memory, discarded on restart. No database or cron scheduler in V2.

## V2.1 functional extensions

- Admin Run Now starts a background `asyncio` job on the single server instance. A short-polling endpoint exposes actual collector and per-agent stage statuses; messages are sanitized and log payloads are only returned after analysis.
- A private, in-process scheduler triggers runs every configured 5–60 minutes **only while awake**.
- RCA evidence and agent traces are stored via `backend/app/store.py` in SQLite locally or externally managed PostgreSQL (recommended on Render Free).
- The private Connections tab accepts selectors and write-only runtime credentials; the AI Settings tab accepts a write-only model key and explicit LLM opt-in. Public demo lock prevents their use.
- Automatic AI RCA is OFF by default. When opted in, at most one optional remote model synthesis request is attempted per incident-producing run; its draft is stored separately from deterministic RCA and must be reviewed.
- When React has not been compiled, FastAPI serves `frontend/fallback.html`, a dependency-free browser UI using the same FastAPI API. Deployment Docker builds React and serves the compiled UI.
