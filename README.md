# LogFix AI V2.1 — Runnable multi-cloud observability + code assistant

**This is the revised working MVP**, based on LogFix AI V2. The dashboard now includes **Run Now**, a server-side scheduler, cloud connection/resource forms, protected credential entry, an AI model configuration page, agent execution polling, persisted RCA history with JSON export, and the original read-only repository assistant.

It is **not** Amazon Q, a fully autonomous AI-agent platform, or a production-certified cloud security product. The 11 operations steps and 7 code steps are deterministic/heuristic by default. Optional OpenAI generation can draft a **clearly labeled, human-reviewed RCA** and answer private questions, only when enabled. No commands are run on cloud resources.

## Feature map

| Feature | How it works | Where in the UI |
|---|---|---|
| Cloud log collection | Read-only SDK queries (Azure Log Analytics, AWS CloudWatch, GCP Cloud Logging), latest 30 minutes and up to 100 records/cloud | **Run & Schedule** / **Cloud Connections** |
| Manual execution | Server-side async job with polled progress, status, sanitized warnings and 11 processing stages | **Run & Schedule → Run Now** |
| Auto collection | In-process loop every 5/10/15/30/60 minutes **while the server is awake** | **Run & Schedule** |
| Live incoming logs | Logs appear after collection finishes; no streaming subscription or tailing | **Log Explorer** |
| Agent health/trace | Each actual stage's completion, timing and errors from the most recent run; public demo shows deterministic completed stages | **Agent Monitor** / **Run & Schedule** |
| RCA archive | Sanitized incidents, evidence log IDs, confidence context, agent trace; exported JSON | **RCA Archive** |
| Cloud configuration | Workspace/table, region/log group, GCP project plus write-only credentials and query test button | **Cloud Connections** |
| AI key/config | Write-only OpenAI key, model name, enable toggle, optional **automatic RCA on collection**, connectivity test | **AI Settings** |
| Code assistant | Read-only repository snapshot search, static findings and cited source lines. Admin-only ZIP uploads | **Code Assistant** |

**Public demo**: `PUBLIC_DEMO_ONLY=true` is always safe synthetic data; visiting the URL needs no credentials. The Run Now button re-analyzes samples. Cloud administration, archive and model-key entry are intentionally disabled.

**Private mode**: `PUBLIC_DEMO_ONLY=false` plus a strong `APP_ADMIN_KEY` enables the admin UI and actual connectors. Do **not** put this private mode on an unauthenticated public website: an admin key by itself is not enterprise authentication. Use a trusted local system or add an access gateway (SSO/IAP/VPN) for remote access.

## Prerequisites

- Python 3.11 or higher.
- Node.js 20+ and npm for the *full React frontend*. There is also a **working dependency-free HTML fallback UI** automatically served on `http://localhost:8000` when React hasn't been built.
- For live cloud ingestion, valid IAM read-only identities and cloud logging resources that already receive log events.
- For optional model synthesis, an OpenAI API key with available API credits; **ChatGPT subscriptions do not include API usage**.

## Quick start — full React UI

```bash
python -m venv .venv
# macOS / Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r backend/requirements-cloud.txt
# Terminal A
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# Terminal B
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/health` to FastAPI. The default synthetic demo requires **no keys**. If npm isn't available, run only FastAPI and use http://localhost:8000 to access the local fallback UI with the same backend actions.

To build the full React app for FastAPI hosting:

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Private mode — actual cloud connections

1. Create a strong admin key and set environment variables (or create an ignored `.env` and load it through your shell):

```bash
export PUBLIC_DEMO_ONLY=false
export APP_ADMIN_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# Optional: local file-backed RCA storage, survives normal app restarts:
export DATABASE_URL="sqlite:///$(pwd)/logfix-data.sqlite3"
```

2. Start FastAPI and open **Cloud Connections**, unlock using `APP_ADMIN_KEY`. That unlock is only in the current browser tab's memory.
3. Fill in **resource selectors**, then **save**. Fill in **credential fields**, then **save**. All secrets in the browser form are **write-only and held in backend RAM until process restart**. For restart-safe deployments, configure them as hosting-platform secrets instead. You cannot retrieve current secret values from API endpoints.
4. Click **Test selected clouds**. This executes *real, bounded log queries* and therefore may incur provider costs. A successful query with zero records means connection worked, not that events exist.
5. Navigate to **Run & Schedule**, choose clouds and **Run Now**. The job displays `queued/running/completed/partial/failed`; each connector and processing stage updates its actual status. Once complete, the log explorer, incident view and RCA archive contain the sanitized results.
6. The **RCA Archive** stores saved results in SQLite (local) or PostgreSQL (if configured), and supports a JSON export. Secrets are not saved.

### What to enter in Cloud Connections

| Cloud | Resource selectors | Read-only authentication fields | IAM / access |
|---|---|---|---|
| **Azure** | `AZURE_WORKSPACE_ID` (GUID) and `AZURE_LOG_TABLE` (allowlisted table) | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` or identity from `DefaultAzureCredential` | Log Analytics Data Reader at the target workspace |
| **AWS** | `AWS_REGION`, `AWS_LOG_GROUP` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, or instance/assumed role | `logs:FilterLogEvents` on selected log group |
| **GCP** | `GCP_PROJECT_ID` | Complete `GCP_SERVICE_ACCOUNT_JSON` pasted in the protected admin UI, or Application Default Credentials / workload identity / secret mounted file | `roles/logging.viewer` for target project |

Use **least-privilege read-only** identities, not root/admin access. For Azure/AWS/GCP troubleshooting and example scopes, see `docs/CLOUD_ACCESS.md`.

### Connect OpenAI

1. Open **AI Settings** after unlocking private mode.
2. Paste the API key into the **write-only OpenAI API Key** field and click **Save API key in RAM**, or set `OPENAI_API_KEY` as a Render environment secret.
3. Select a model, e.g. `gpt-4.1-mini`, enable LLM synthesis, and save.
4. **Optionally** enable **Automatically generate AI RCA after each run**. This creates **one model call per run with incidents** (including scheduled runs) and stores the draft alongside deterministic RCA. Default is OFF to prevent unintentional costs.
5. Click **Test AI connection** (consumes a small number of tokens). For Operations AI / Code Assistant private questions, enable the **Use AI for private questions** toggle on the AI Settings page.

The model receives bounded, redacted context; however regex-based sanitization is not a DLP guarantee. Do not send confidential/regulated data to an external AI model without reviewing data handling and policies.

## Persistence and free hosting

The app uses a database for run/RCA history (retaining the most recent 250 runs):

- **SQLite locally:** `DATABASE_URL=sqlite:///...` (default `/tmp/logfix-ai-v2.sqlite3`), persists between app restarts on a local persistent disk.
- **PostgreSQL on Render:** set `DATABASE_URL` to a secret connection string for an external managed Postgres instance, such as **Neon Free**. The included SQLAlchemy + psycopg driver supports PostgreSQL. Database schema initializes automatically. This persistent database connection has only been integration-tested using SQLite; test PostgreSQL connectivity on your infrastructure.
- **Render Free local SQLite will be lost** after service idle spin-down/restart/redeploy; use external Postgres for durable history. Free Render also sleeps after inactivity, so **the in-process scheduler is not 24/7 reliable**. For guaranteed continuous collection, use externally scheduled calls to a private authenticated endpoint on always-on compute/cron or a paid service. Do not rely on a free sleeping host for production monitoring.

## Deploy a shareable free public demo to Render

1. Push the entire extracted folder's contents to the **root** of a GitHub repository (no `.env`, keys or credentials).
2. On Render, New → Web Service → GitHub repository → Docker, **Free** plan. Root Directory blank; Dockerfile path `./Dockerfile`; health path `/health`.
3. Configure `PUBLIC_DEMO_ONLY=true`, `ENABLE_LLM=false`, `AI_RCA_ON_RUN=false`. **Do not configure real-cloud/API credentials** on the public service.
4. Deploy, wait for status Live and open the Render-provided `https://<your-service>.onrender.com` URL. No actual URL is created until you deploy.
5. Public visitors can open **Run & Schedule → Run Now**, explore logs and agent stages and use the fictional coding assistant. Real settings remain locked.

See `docs/DEPLOY_RENDER.md` for detailed GitHub/Render instructions.

## Diagnostics

```bash
pip install -r backend/requirements.txt pytest httpx
python -m pytest backend/tests -q
python scripts/diagnostics.py
```

`backend/tests` includes end-to-end API and mock cloud tests for the scheduler, execution traces, credential redaction, JSON RCA archives, DB persistence across an app restart and optional AI synthesis. **Mocked cloud responses are not real cloud validation**. Use **Cloud Connections → Test selected clouds** with your real account to verify permissions and connectivity.

See [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md) for what was tested and the limitations of this deliverable.

## Security limits

This is a demo/MVP, not audited production software. The protected admin UI uses a shared API key, not SSO/MFA; do not deploy real-cloud mode to an exposed Render URL without an independent authenticated gateway. Stored sanitized RCA may still contain sensitive data not caught by regex redaction. The scheduler runs in one process; multiple workers/replicas aren't supported. Log collectors are **bounded pull queries**, not low-latency streaming subscribers. The App does not automatically remediate infrastructure or send alerts.

MIT license; not affiliated with Amazon or Amazon Q.
