# Functional diagnostics and acceptance report

## Validated here (2026-10-16)

- **33 Python pytest cases passed:** existing operations and code analysis, API authentication, ZIP upload protections, sanitization, connector mocks, public demo lock, new credential settings, Run Now job, per-agent trace, SQLite persistence after a fresh app instance, scheduler API and scheduler tick, optional AI RCA with a mocked provider.
- **Live localhost FastAPI smoke test:** `/health` returned HTTP 200; `/` returned HTTP 200 and a self-contained HTML fallback dashboard; `POST /api/demo/run` returned 12 synthetic logs, 11 operations stages and 3 incidents.
- **Frontend syntax:** React `src/App.jsx` parsed by the TypeScript JSX parser with no parse diagnostics; the standalone fallback page's external JavaScript passed `node --check`, and the fallback script is served under a restrictive Content-Security-Policy.
- **Security paths:** admin APIs reject invalid/missing credentials; public-demo lock rejects live collection, private scheduling/config mutation and secret entry even with admin key; credentials and unredacted log patterns do not appear in test API responses, stored RCA or AI evidence.

## Not validated here / required before live use

- **Real Azure/AWS/GCP access:** No user's cloud IAM credentials, project IDs or workspace IDs were available. The integration tests use mocks; press **Test selected clouds** in your private instance with real read-only IAM to verify.
- **Real OpenAI call:** The model API was tested with a stub to check enablement, routing and saved RCA. Real network/API billing/permissions/response were not tested; use the protected **Test AI connection** action.
- **React runtime build and Docker container:** `npm install` couldn't reach npmjs.org in this execution environment (`EAI_AGAIN`), so an actual React bundle and complete Docker build were **not** executed here. `npm run build` is part of GitHub CI and Render Docker build. A working, dependency-free HTML fallback dashboard is included for local API use.
- **Visual browser end-to-end:** Headless Chromium was blocked from local HTTP by execution-environment browser controls; HTTP endpoint tests and JS parsing succeeded, but live in-browser screenshot/run testing is pending on your computer.
- **PostgreSQL persistence:** SQLAlchemy code for PostgreSQL is provided, but tests exercised SQLite only. Configure Neon or another Postgres service then verify with two restarts.
- **Long-term scheduler reliability:** In-process scheduler tick is tested while the server is awake. Render Free spins down and cannot promise uninterrupted schedules. For 24/7 monitoring change hosting/scheduling architecture.

## Actual-account acceptance checklist

1. On a **private** instance, enter credentials for each cloud with minimal IAM and save resource selectors.
2. Test each connector separately. A successful result with 0 logs confirms the request was authorized, not that logs are flowing.
3. Generate a known test ERROR log in each account (or use an existing event from the last 30 minutes), click **Run Now**, select one cloud, and verify the event is in **Log Explorer**.
4. Confirm the corresponding trace reports the provider connector status, 11 stages, and a root-cause hypothesis linked to log evidence. Verify the RCA does not contain secrets.
5. Enable scheduler for a short interval in an **awake** development service, wait, and check **RCA Archive** for a scheduled run.
6. Restart the service. With an external PostgreSQL `DATABASE_URL`, verify history remains and UI-entered *RAM-only credentials* need reentry; move them to environment secrets for continuity.
7. In AI Settings, enter key, enable LLM, run **Test AI connection**, and optionally enable automatic RCA. Inspect stored draft and provider billing.
8. Confirm access denial with no/incorrect admin key and test from a separate browser/incognito window. Keep public synthetic demo lock ON for shared URLs.
