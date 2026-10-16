# Security boundaries

- Public demo mode (`PUBLIC_DEMO_ONLY=true`) exposes **only synthetic** log/code fixtures. Protected writes, private uploads, schedules, secrets, real cloud queries and model tests are blocked by a **server-side** guard.
- Private mode (`PUBLIC_DEMO_ONLY=false`) requires an `APP_ADMIN_KEY` to call `/api/admin/*`; this single shared secret is **not** enterprise authentication. Put a separate private deployment behind SSO/IAP/VPN; do not show real logs through a public anonymous URL.
- Cloud credentials and `OPENAI_API_KEY` may be supplied via hosting secret environment variables (preferred) or protected UI; UI inputs are **write-only and held in RAM**, never returned through the API, not persisted and not cached in browser storage.
- Connectors have read-only SDK calls; no shell commands or cloud mutations are performed. Keep cloud-side IAM permissions least-privilege.
- Remote AI is disabled by default. Both the API key and explicit feature enablement are required. Automatic AI RCA requires another opt-in and will consume tokens on scheduled runs if enabled.
- Only sanitized log messages are saved in the DB; however regex sanitization cannot guarantee data protection for all formats. Add DLP, audit, retention and access controls before sensitive use.
- SQLAlchemy sends stored runs to SQLite or configured PostgreSQL. Secure the database with TLS, credentials and network restrictions. Archive exports remain confidential.
- Per-user identity, CSRF-hardening, rate limits, audit logging, robust secret rotation and penetration testing are beyond this MVP. Don't treat it as a production-secure SaaS.
