# Delivery plan

## V2 demo (included)
- Unified React UI and FastAPI API
- Demonstration of AWS/Azure/GCP normalized log ingestion
- 11 observable deterministic incident stages
- Repository ZIP ingestion + 7 observable static analysis stages
- Log-evidence-grounded incident Q&A + repository line references
- Cross-workspace keyword correlation hints, not proven causality
- Admin-only optional LLM-assisted synthesis
- Container + Render deployment, automated backend tests

## V2.1 private pilot
- Security gateway with OIDC/MFA, identity federation for each cloud
- SDK pagination / resilient backoff / quota testing, encrypted secrets and provider health
- Persistent database, scheduler on a service that doesn't sleep, incident history
- Metrics, tracing and deployment change correlation

## V3 production-grade
- Runbook RAG, multi-turn tool plans with checkpoints, evaluation dataset
- GitHub App PR-only suggestions and test validation in isolated ephemeral sandboxes
- CMDB / ITSM integration, human approval for remediation, audit log
- SLO-based alerts, RBAC, tenant partitioning and compliance review
